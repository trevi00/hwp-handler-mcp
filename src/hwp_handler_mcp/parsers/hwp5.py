"""HWP 5.x 네이티브 파서 (olefile + zlib + struct).

근거: .planning/research/RHWP-HWP5-PARSER.md §1-9 + §7 의사코드.
"""

from __future__ import annotations

import io
import logging
import struct
import zlib
from collections.abc import Iterator

import olefile

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import (
    BreakKind,
    Document,
    Format,
    Metadata,
    Paragraph,
    Run,
    Section,
    SecurityFlags,
)
from hwp_handler_mcp.parsers.detect import parse_hwp5_flags
from hwp_handler_mcp.parsers.summary import read_hwp5_summary

log = logging.getLogger(__name__)

HWPTAG_BEGIN = 0x010
HWPTAG_DOCUMENT_PROPERTIES = 0x010
HWPTAG_PARA_HEADER = 0x042  # 66
HWPTAG_PARA_TEXT = 0x043  # 67


def parse_hwp5(path_or_bytes: str | bytes) -> Document:
    """HWP5 바이너리를 IR Document로 파싱.

    암호화/배포본/DRM은 명시적으로 거부.
    """
    if isinstance(path_or_bytes, str):
        ole = olefile.OleFileIO(path_or_bytes)
    else:
        ole = olefile.OleFileIO(io.BytesIO(path_or_bytes))

    try:
        if not ole.exists("FileHeader"):
            raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="FileHeader 스트림 없음")

        hdr = ole.openstream("FileHeader").read()
        version, flags = parse_hwp5_flags(hdr)

        _enforce_security_policy(flags)

        section_streams = _collect_section_streams(ole, flags.compressed)
        sections = tuple(_parse_section(idx, raw) for idx, raw in enumerate(section_streams))

        summary = read_hwp5_summary(ole)
        metadata = Metadata(
            title=summary.get("title"),
            author=summary.get("author"),
            last_author=summary.get("last_author"),
            created_at=summary.get("created_at"),
            modified_at=summary.get("modified_at"),
            section_count=len(sections),
            page_count=summary.get("page_count"),
            raw=summary.get("raw", {}),
        )

        return Document(
            format=Format.HWP5,
            version=version,
            flags=flags,
            metadata=metadata,
            sections=sections,
        )
    finally:
        ole.close()


def _enforce_security_policy(flags: SecurityFlags) -> None:
    """REQUIREMENTS.md §3.3 거부 케이스를 강제."""
    if flags.distribution:
        raise_hwp_error(ErrorCode.DISTRIBUTION_PROTECTED)
    if flags.drm:
        raise_hwp_error(ErrorCode.DRM_PROTECTED)
    if flags.public_key_encrypted:
        raise_hwp_error(ErrorCode.PKI_ENCRYPTED)
    if flags.encrypted:
        # 암호화 문서 복호화는 미지원 — 명시적으로 거부한다.
        raise_hwp_error(ErrorCode.PASSWORD_REQUIRED)


def _collect_section_streams(ole: olefile.OleFileIO, compressed: bool) -> list[bytes]:
    """BodyText/Section{N} 스트림을 enumerate해 압축 해제된 바이트 리스트 반환."""
    streams: list[bytes] = []
    idx = 0
    while True:
        path = f"BodyText/Section{idx}"
        if not ole.exists(path):
            # /Section{N} 구버전 호환 (rhwp cfb_reader.rs:125)
            legacy = f"Section{idx}"
            if ole.exists(legacy):
                raw = ole.openstream(legacy).read()
            else:
                break
        else:
            raw = ole.openstream(path).read()
        if compressed:
            raw = _decompress(raw)
        streams.append(raw)
        idx += 1
    return streams


def _decompress(raw: bytes) -> bytes:
    """raw deflate (wbits=-15) 우선, 표준 zlib 폴백 (rhwp cfb_reader.rs:550-568)."""
    try:
        return zlib.decompress(raw, wbits=-15)
    except zlib.error:
        return zlib.decompress(raw)


def _parse_section(index: int, data: bytes) -> Section:
    """단일 섹션 바이트 → Section IR.

    rhwp body_text.rs 패턴: PARA_HEADER 만나면 새 단락 시작, PARA_TEXT는 텍스트 페이로드.
    """
    paragraphs: list[Paragraph] = []
    current_text: list[str] = []
    current_break: BreakKind = BreakKind.NONE
    para_index = 0

    for tag_id, _level, body in _read_records(data):
        if tag_id == HWPTAG_PARA_HEADER:
            if current_text or paragraphs:
                paragraphs.append(_flush_paragraph(para_index, current_text, current_break))
                para_index += 1
            current_text = []
            current_break = _parse_break_type(body)
        elif tag_id == HWPTAG_PARA_TEXT:
            current_text.append(_decode_para_text(body))

    # 마지막 단락 flush
    if current_text:
        paragraphs.append(_flush_paragraph(para_index, current_text, current_break))

    return Section(index=index, paragraphs=tuple(paragraphs))


def _flush_paragraph(index: int, text_chunks: list[str], break_after: BreakKind) -> Paragraph:
    text = "".join(text_chunks)
    return Paragraph(
        index=index,
        runs=(Run(text=text),) if text else (),
        break_after=break_after,
    )


def _parse_break_type(para_header_body: bytes) -> BreakKind:
    """PARA_HEADER 페이로드의 break_type 비트 해석.

    레이아웃 (rhwp body_text.rs:213-247):
      offset 0..4: u32 nChars
      offset 4..8: u32 controlMask
      offset 8..10: u16 paraShapeId
      offset 10: u8 styleId
      offset 11: u8 breakType (bits: 0x01=섹션, 0x02=다단, 0x04=쪽, 0x08=단)
    """
    if len(para_header_body) < 12:
        return BreakKind.NONE
    break_byte = para_header_body[11]
    if break_byte & 0x04:
        return BreakKind.PAGE
    if break_byte & 0x08:
        return BreakKind.COLUMN
    if break_byte & 0x01:
        return BreakKind.SECTION
    return BreakKind.NONE


def _read_records(data: bytes) -> Iterator[tuple[int, int, bytes]]:
    """레코드 평면 파서. (tag_id, level, body) 시퀀스 반환.

    헤더 32비트 비트 필드: tag_id(10) + level(10) + size(12).
    size == 0xFFF이면 다음 4바이트가 실제 size.
    """
    pos = 0
    n = len(data)
    while pos + 4 <= n:
        header = struct.unpack_from("<I", data, pos)[0]
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            if pos + 4 > n:
                log.warning("HWP5: 확장 size 헤더 잘림. 잔여 %d 바이트", n - pos)
                return
            size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if pos + size > n:
            log.warning("HWP5: 레코드 size %d > 잔여 %d. 종료", size, n - pos)
            return
        yield tag_id, level, data[pos : pos + size]
        pos += size


# 인라인 컨트롤 분류 (rhwp body_text.rs:380-398):
# - inline (4-9, 19-20) + extended (1-3, 11-12, 14-18, 21-23) = 16 byte
# - char (0, 10, 13, 24-31) = 2 byte
_BIG_CONTROL = (set(range(1, 10)) | {11, 12} | set(range(14, 24))) - {9, 10}
_SPECIAL_CHAR_MAP: dict[int, str] = {
    0x18: " ",  # 묶음 빈칸
    0x19: " ",  # 고정폭 빈칸
    0x1E: "-",  # 하이픈
    0x1F: " ",  # FIGURE SPACE
}


def _decode_para_text(data: bytes) -> str:
    """PARA_TEXT 바이트 → 단락 텍스트. UTF-16LE + 인라인 컨트롤 처리."""
    out: list[str] = []
    pos = 0
    n = len(data)
    while pos + 1 < n:
        ch = struct.unpack_from("<H", data, pos)[0]
        if ch == 0x0000:
            pos += 2
        elif ch == 0x0009:
            out.append("\t")
            pos += 16
        elif ch == 0x000A:
            out.append("\n")
            pos += 2
        elif ch == 0x000D:
            break  # 문단 끝
        elif ch in _BIG_CONTROL:
            if ch == 0x0012:  # AutoNumber placeholder
                out.append(" ")
            pos += 16
        elif ch < 0x0020:
            if ch in _SPECIAL_CHAR_MAP:
                out.append(_SPECIAL_CHAR_MAP[ch])
            pos += 2
        else:
            # 서로게이트 페어 처리
            if 0xD800 <= ch <= 0xDBFF and pos + 3 < n:
                low = struct.unpack_from("<H", data, pos + 2)[0]
                if 0xDC00 <= low <= 0xDFFF:
                    cp = 0x10000 + ((ch - 0xD800) << 10) + (low - 0xDC00)
                    out.append(chr(cp))
                    pos += 4
                    continue
            out.append(chr(ch))
            pos += 2
    return "".join(out)
