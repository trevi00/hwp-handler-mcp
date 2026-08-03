from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest

from hwp_handler_mcp._compat import McpError
from hwp_handler_mcp.tools.attach import (
    _guess_media_type,
    list_attachments_impl,
    read_attachment_impl,
)


def test_guess_media_type_png() -> None:
    assert _guess_media_type("foo.png", b"") == "image/png"


def test_guess_media_type_by_magic_when_extension_unknown() -> None:
    assert _guess_media_type("foo.bin", b"\x89PNG\r\n\x1a\n") == "image/png"


def test_guess_media_type_jpeg_by_magic() -> None:
    assert _guess_media_type("foo.bin", b"\xff\xd8\xff") == "image/jpeg"


def test_guess_media_type_default() -> None:
    assert _guess_media_type("foo.bin", b"random") == "application/octet-stream"


def test_list_attachments_hwpx(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("BinData/image1.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        z.writestr("BinData/note.txt", b"hello attachment")
        z.writestr("Contents/header.xml", "<header/>")  # not BinData

    result = list_attachments_impl(str(target))
    assert result.total_count == 2
    storage_ids = {a.storage_id for a in result.attachments}
    assert "BinData/image1.png" in storage_ids
    assert "BinData/note.txt" in storage_ids
    image = next(a for a in result.attachments if a.filename == "image1.png")
    assert image.is_image
    assert image.media_type == "image/png"


def test_list_attachments_password_rejected(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
    with pytest.raises(McpError) as exc_info:
        list_attachments_impl(str(target), password="x")  # noqa: S106
    assert exc_info.value.error.data["code"] == "PASSWORD_REQUIRED"


def test_read_attachment_hwpx_returns_base64(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    payload = b"\x89PNG\r\n\x1a\n" + b"some image data" * 5
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("BinData/image1.png", payload)

    result = read_attachment_impl(str(target), storage_id="BinData/image1.png")
    decoded = base64.b64decode(result.content_base64)
    assert decoded == payload
    assert result.size_bytes == len(payload)
    assert result.filename == "image1.png"
    assert result.media_type == "image/png"


def test_read_attachment_not_found(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
    with pytest.raises(McpError) as exc_info:
        read_attachment_impl(str(target), storage_id="BinData/missing.png")
    assert exc_info.value.error.data["code"] == "ATTACHMENT_NOT_FOUND"


def test_read_attachment_too_large(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    payload = b"X" * 1024
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
        z.writestr("BinData/big.bin", payload)
    with pytest.raises(McpError) as exc_info:
        read_attachment_impl(str(target), storage_id="BinData/big.bin", max_size_bytes=512)
    assert exc_info.value.error.data["code"] == "ATTACHMENT_TOO_LARGE"
