from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwp_handler_mcp._compat import McpError
from hwp_handler_mcp.tools.inspect import inspect_structure_impl


def test_inspect_structure_invalid_file_raises(tmp_path: Path) -> None:
    target = tmp_path / "garbage.bin"
    target.write_bytes(b"not a valid file")
    with pytest.raises(McpError) as exc_info:
        inspect_structure_impl(str(target))
    assert exc_info.value.error.data["code"] == "INVALID_FORMAT"


def test_inspect_structure_hwpx_lists_streams(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("Contents/header.xml", "<header/>")
        z.writestr("BinData/image1.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    report = inspect_structure_impl(str(target))
    assert report.format == "hwpx"
    names = {s.name for s in report.streams}
    assert "Contents/content.hpf" in names
    assert "Contents/header.xml" in names
    assert "BinData/image1.png" in names


def test_inspect_structure_hwpx_with_preview(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    payload = b"hello world payload"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("readme.txt", payload)
    report = inspect_structure_impl(str(target), include_data_preview=True)
    readme = next(s for s in report.streams if s.name == "readme.txt")
    assert readme.preview_hex is not None
    assert payload[:64].hex() == readme.preview_hex


def test_inspect_structure_hwpx_sha256_consistent(tmp_path: Path) -> None:
    import hashlib

    target = tmp_path / "fake.hwpx"
    payload = b"some content for hashing"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("data.bin", payload)
    report = inspect_structure_impl(str(target))
    data_entry = next(s for s in report.streams if s.name == "data.bin")
    assert data_entry.sha256 == hashlib.sha256(payload).hexdigest()
