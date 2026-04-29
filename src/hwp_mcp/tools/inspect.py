"""detect_format + inspect_structure MCP 도구."""
from __future__ import annotations

import hashlib
import struct
import time
import zipfile
from collections import Counter
from pathlib import Path

import olefile
from pydantic import BaseModel, Field

from hwp_mcp.errors import ErrorCode, raise_hwp_error
from hwp_mcp.ir import Format
from hwp_mcp.parsers.detect import detect_magic, parse_hwp5_flags


class FormatInfo(BaseModel):
    path: str
    format: Format
    version: str | None = None
    encrypted: bool = False
    distribution: bool = False
    drm: bool = False
    digital_signature: bool = False
    public_key_encrypted: bool = False
    script: bool = False
    file_size: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


def detect_format_impl(path: str) -> FormatInfo:
    """detect_format MCP 도구의 구현."""
    started = time.perf_counter()
    p = Path(path)
    fmt = detect_magic(p)
    size = p.stat().st_size
    warnings: list[str] = []

    version: str | None = None
    flags_kwargs: dict[str, bool] = {}

    if fmt == Format.HWP5:
        try:
            ole = olefile.OleFileIO(str(p))
            try:
                if not ole.exists("FileHeader"):
                    raise_hwp_error(
                        ErrorCode.INVALID_FORMAT, detail="FileHeader 스트림 없음"
                    )
                hdr = ole.openstream("FileHeader").read()
                version, flags = parse_hwp5_flags(hdr)
                flags_kwargs = {
                    "encrypted": flags.encrypted,
                    "distribution": flags.distribution,
                    "drm": flags.drm,
                    "digital_signature": flags.digital_signature,
                    "public_key_encrypted": flags.public_key_encrypted,
                    "script": flags.script,
                }
            finally:
                ole.close()
        except OSError as exc:
            raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"OLE 파싱 실패: {exc}")

    elif fmt == Format.HWPX:
        version = "HWPX"
        warnings.append("HWPX 버전은 별도 파싱 필요 (현재 'HWPX' 고정)")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return FormatInfo(
        path=str(p),
        format=fmt,
        version=version,
        file_size=size,
        elapsed_ms=elapsed_ms,
        warnings=warnings,
        **flags_kwargs,
    )


class StreamEntry(BaseModel):
    name: str
    size: int
    compressed_size: int | None = None
    sha256: str
    preview_hex: str | None = None


class StructureReport(BaseModel):
    path: str
    format: Format
    streams: list[StreamEntry]
    record_summary: dict[str, int] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: int


def inspect_structure_impl(path: str, include_data_preview: bool = False) -> StructureReport:
    """파일을 변형하지 않고 컨테이너 구조를 dump."""
    started = time.perf_counter()
    p = Path(path)
    fmt = detect_magic(p)
    warnings: list[str] = []
    streams: list[StreamEntry] = []
    record_summary: dict[str, int] = {}
    flags_dict: dict[str, bool] = {}

    if fmt == Format.HWP5:
        ole = olefile.OleFileIO(str(p))
        try:
            for stream_path_parts in ole.listdir(streams=True, storages=False):
                stream_path = "/".join(stream_path_parts)
                data = ole.openstream(stream_path).read()
                streams.append(
                    StreamEntry(
                        name=stream_path,
                        size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        preview_hex=data[:64].hex() if include_data_preview else None,
                    )
                )

            if ole.exists("FileHeader"):
                _, sf = parse_hwp5_flags(ole.openstream("FileHeader").read())
                flags_dict = {
                    "compressed": sf.compressed,
                    "encrypted": sf.encrypted,
                    "distribution": sf.distribution,
                    "drm": sf.drm,
                    "digital_signature": sf.digital_signature,
                    "public_key_encrypted": sf.public_key_encrypted,
                    "script": sf.script,
                }
                record_summary = _summarize_records(ole, sf.compressed)
        finally:
            ole.close()

    elif fmt == Format.HWPX:
        with zipfile.ZipFile(str(p)) as z:
            for info in z.infolist():
                with z.open(info) as f:
                    data = f.read()
                streams.append(
                    StreamEntry(
                        name=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        sha256=hashlib.sha256(data).hexdigest(),
                        preview_hex=data[:64].hex() if include_data_preview else None,
                    )
                )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return StructureReport(
        path=str(p),
        format=fmt,
        streams=streams,
        record_summary=record_summary,
        flags=flags_dict,
        warnings=warnings,
        elapsed_ms=elapsed_ms,
    )


def _summarize_records(ole: olefile.OleFileIO, compressed: bool) -> dict[str, int]:
    """DocInfo + BodyText/Section{N}의 record tag 카운트."""
    import zlib

    counter: Counter[str] = Counter()

    def _count(stream_path: str) -> None:
        if not ole.exists(stream_path):
            return
        raw = ole.openstream(stream_path).read()
        if compressed:
            try:
                raw = zlib.decompress(raw, wbits=-15)
            except zlib.error:
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    return
        pos = 0
        n = len(raw)
        while pos + 4 <= n:
            header = struct.unpack_from("<I", raw, pos)[0]
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF
            pos += 4
            if size == 0xFFF:
                if pos + 4 > n:
                    return
                size = struct.unpack_from("<I", raw, pos)[0]
                pos += 4
            counter[f"0x{tag_id:03X}"] += 1
            pos += size

    _count("DocInfo")
    idx = 0
    while True:
        if not ole.exists(f"BodyText/Section{idx}"):
            break
        _count(f"BodyText/Section{idx}")
        idx += 1

    return dict(counter)
