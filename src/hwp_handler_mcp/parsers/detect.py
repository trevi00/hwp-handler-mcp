from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import Format, SecurityFlags

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
HWP5_SIGNATURE = b"HWP Document File"
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB


def detect_magic(path: Path) -> Format:
    """4바이트 + 추가 매직으로 포맷 감지."""
    if not path.is_file():
        raise_hwp_error(ErrorCode.FILE_NOT_FOUND, detail=str(path))
    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise_hwp_error(
            ErrorCode.FILE_TOO_LARGE,
            extra={"size": size, "limit": MAX_FILE_SIZE},
        )

    with path.open("rb") as f:
        header = f.read(8)

    if header.startswith(OLE2_MAGIC):
        # HWP5 vs HWP3 판별 — FileHeader 시그니처 확인 필요
        # 실제 구현은 olefile 의존
        return Format.HWP5
    if header.startswith(ZIP_MAGIC):
        return _detect_zip_format(path)

    raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=str(path))
    raise AssertionError("unreachable")  # ruff RET503 — raise_hwp_error is NoReturn


def _detect_zip_format(path: Path) -> Format:
    """ZIP인 경우 HWPX 여부 확인. content.hpf가 있으면 HWPX."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "Contents/content.hpf" in names or any("content.hpf" in n for n in names):
                return Format.HWPX
    except zipfile.BadZipFile:
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"손상된 ZIP: {path}")
    raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"HWPX 아님: {path}")
    raise AssertionError("unreachable")  # ruff RET503


def parse_hwp5_flags(file_header_bytes: bytes) -> tuple[str, SecurityFlags]:
    """HWP5 FileHeader 256바이트 → (version, SecurityFlags)."""
    if len(file_header_bytes) < 40:
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="FileHeader < 40 bytes")
    if not file_header_bytes[:17].startswith(HWP5_SIGNATURE):
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="HWP5 시그니처 불일치")

    revision = file_header_bytes[32]
    build = file_header_bytes[33]
    minor = file_header_bytes[34]
    major = file_header_bytes[35]
    flags_u32 = struct.unpack_from("<I", file_header_bytes, 36)[0]

    version = f"{major}.{minor}.{build}.{revision}"
    flags = SecurityFlags(
        compressed=bool(flags_u32 & 0x001),
        encrypted=bool(flags_u32 & 0x002),
        distribution=bool(flags_u32 & 0x004),
        script=bool(flags_u32 & 0x008),
        drm=bool(flags_u32 & 0x010),
        digital_signature=bool(flags_u32 & 0x080),
        public_key_encrypted=bool(flags_u32 & 0x100),
    )
    return version, flags
