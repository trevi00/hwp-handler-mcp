from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwp_handler_mcp._compat import McpError
from hwp_handler_mcp.ir import Format
from hwp_handler_mcp.parsers.detect import (
    HWP5_SIGNATURE,
    OLE2_MAGIC,
    ZIP_MAGIC,
    detect_magic,
    parse_hwp5_flags,
)


def test_detect_invalid_file_raises(tmp_path: Path) -> None:
    target = tmp_path / "garbage.bin"
    target.write_bytes(b"not a hwp file at all")
    with pytest.raises(McpError) as exc_info:
        detect_magic(target)
    assert exc_info.value.error.data["code"] == "INVALID_FORMAT"


def test_detect_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(McpError) as exc_info:
        detect_magic(tmp_path / "does_not_exist.hwp")
    assert exc_info.value.error.data["code"] == "FILE_NOT_FOUND"


def test_detect_ole2_magic_returns_hwp5(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwp"
    target.write_bytes(OLE2_MAGIC + b"\x00" * 1024)
    assert detect_magic(target) == Format.HWP5


def test_detect_zip_without_content_hpf_raises(tmp_path: Path) -> None:
    target = tmp_path / "fake.zip"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("readme.txt", "hello")
    with pytest.raises(McpError) as exc_info:
        detect_magic(target)
    assert exc_info.value.error.data["code"] == "INVALID_FORMAT"


def test_detect_hwpx_with_content_hpf(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
    assert detect_magic(target) == Format.HWPX


def test_parse_hwp5_flags_signature_mismatch() -> None:
    hdr = b"\x00" * 256
    with pytest.raises(McpError) as exc_info:
        parse_hwp5_flags(hdr)
    assert exc_info.value.error.data["code"] == "INVALID_FORMAT"


def test_parse_hwp5_flags_compressed_bit() -> None:
    hdr = bytearray(256)
    hdr[: len(HWP5_SIGNATURE)] = HWP5_SIGNATURE
    hdr[35] = 5  # major
    hdr[34] = 1  # minor
    hdr[33] = 0  # build
    hdr[32] = 0  # revision
    hdr[36:40] = (0x001).to_bytes(4, "little")
    version, flags = parse_hwp5_flags(bytes(hdr))
    assert version == "5.1.0.0"
    assert flags.compressed is True
    assert flags.encrypted is False


def test_parse_hwp5_flags_encrypted_bit() -> None:
    hdr = bytearray(256)
    hdr[: len(HWP5_SIGNATURE)] = HWP5_SIGNATURE
    hdr[35] = 5
    hdr[34] = 1
    hdr[36:40] = (0x002).to_bytes(4, "little")
    _, flags = parse_hwp5_flags(bytes(hdr))
    assert flags.encrypted is True
    assert flags.distribution is False


def test_parse_hwp5_flags_distribution_bit() -> None:
    hdr = bytearray(256)
    hdr[: len(HWP5_SIGNATURE)] = HWP5_SIGNATURE
    hdr[35] = 5
    hdr[34] = 1
    hdr[36:40] = (0x004).to_bytes(4, "little")
    _, flags = parse_hwp5_flags(bytes(hdr))
    assert flags.distribution is True


def test_zip_magic_constant() -> None:
    assert ZIP_MAGIC == b"PK\x03\x04"
