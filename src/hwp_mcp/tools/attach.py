"""list_attachments + read_attachment MCP 도구."""
from __future__ import annotations

import base64
import mimetypes
import time
import zipfile
from pathlib import Path

import olefile
from pydantic import BaseModel, Field

from hwp_mcp.errors import ErrorCode, raise_hwp_error
from hwp_mcp.ir import Format
from hwp_mcp.parsers.detect import detect_magic


class AttachmentInfo(BaseModel):
    storage_id: str
    filename: str
    media_type: str
    size_bytes: int
    is_image: bool
    is_ole: bool


class ListAttachmentsResult(BaseModel):
    attachments: list[AttachmentInfo]
    total_count: int
    total_size_bytes: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


class AttachmentContent(BaseModel):
    storage_id: str
    filename: str
    media_type: str
    size_bytes: int
    content_base64: str
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


_IMAGE_MIME_PREFIX = "image/"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def list_attachments_impl(path: str, password: str | None = None) -> ListAttachmentsResult:
    """문서 안 첨부 파일(이미지/OLE/차트) 목록."""
    started = time.perf_counter()
    p = Path(path)
    fmt = detect_magic(p)

    if password is not None:
        raise_hwp_error(
            ErrorCode.PASSWORD_REQUIRED,
            detail="비밀번호 복호화는 Phase B에서 지원 예정",
        )

    if fmt == Format.HWP5:
        attachments = _list_hwp5_attachments(p)
    elif fmt == Format.HWPX:
        attachments = _list_hwpx_attachments(p)
    else:
        raise_hwp_error(ErrorCode.UNSUPPORTED_VERSION, detail=f"미지원 포맷: {fmt}")

    total_size = sum(a.size_bytes for a in attachments)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ListAttachmentsResult(
        attachments=attachments,
        total_count=len(attachments),
        total_size_bytes=total_size,
        elapsed_ms=elapsed_ms,
    )


def read_attachment_impl(
    path: str,
    storage_id: str,
    password: str | None = None,
    max_size_bytes: int = 5_242_880,
) -> AttachmentContent:
    """특정 첨부 1개의 raw bytes를 base64로 반환."""
    started = time.perf_counter()
    p = Path(path)
    fmt = detect_magic(p)

    if password is not None:
        raise_hwp_error(
            ErrorCode.PASSWORD_REQUIRED,
            detail="비밀번호 복호화는 Phase B에서 지원 예정",
        )

    if fmt == Format.HWP5:
        data, filename, media_type = _read_hwp5_attachment(p, storage_id)
    elif fmt == Format.HWPX:
        data, filename, media_type = _read_hwpx_attachment(p, storage_id)
    else:
        raise_hwp_error(ErrorCode.UNSUPPORTED_VERSION, detail=f"미지원 포맷: {fmt}")

    if len(data) > max_size_bytes:
        raise_hwp_error(
            ErrorCode.ATTACHMENT_TOO_LARGE,
            extra={"size": len(data), "limit": max_size_bytes},
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return AttachmentContent(
        storage_id=storage_id,
        filename=filename,
        media_type=media_type,
        size_bytes=len(data),
        content_base64=base64.b64encode(data).decode("ascii"),
        elapsed_ms=elapsed_ms,
    )


def _list_hwp5_attachments(path: Path) -> list[AttachmentInfo]:
    out: list[AttachmentInfo] = []
    ole = olefile.OleFileIO(str(path))
    try:
        for parts in ole.listdir(streams=True, storages=False):
            if not parts or parts[0] != "BinData":
                continue
            stream_path = "/".join(parts)
            data = ole.openstream(stream_path).read()
            filename = parts[-1]
            media_type = _guess_media_type(filename, data)
            out.append(
                AttachmentInfo(
                    storage_id=filename,
                    filename=filename,
                    media_type=media_type,
                    size_bytes=len(data),
                    is_image=media_type.startswith(_IMAGE_MIME_PREFIX),
                    is_ole=data.startswith(_OLE_MAGIC),
                )
            )
    finally:
        ole.close()
    return out


def _list_hwpx_attachments(path: Path) -> list[AttachmentInfo]:
    out: list[AttachmentInfo] = []
    with zipfile.ZipFile(str(path)) as z:
        for info in z.infolist():
            if not info.filename.startswith("BinData/"):
                continue
            with z.open(info) as f:
                head = f.read(min(info.file_size, 16))
            filename = Path(info.filename).name
            media_type = _guess_media_type(filename, head)
            out.append(
                AttachmentInfo(
                    storage_id=info.filename,
                    filename=filename,
                    media_type=media_type,
                    size_bytes=info.file_size,
                    is_image=media_type.startswith(_IMAGE_MIME_PREFIX),
                    is_ole=head.startswith(_OLE_MAGIC),
                )
            )
    return out


def _read_hwp5_attachment(path: Path, storage_id: str) -> tuple[bytes, str, str]:
    """storage_id는 파일명 (예: BIN0001.png)."""
    ole = olefile.OleFileIO(str(path))
    try:
        candidate = f"BinData/{storage_id}"
        if not ole.exists(candidate):
            raise_hwp_error(ErrorCode.ATTACHMENT_NOT_FOUND, detail=storage_id)
        data = ole.openstream(candidate).read()
        return data, storage_id, _guess_media_type(storage_id, data)
    finally:
        ole.close()


def _read_hwpx_attachment(path: Path, storage_id: str) -> tuple[bytes, str, str]:
    """storage_id는 ZIP 내부 경로 (예: BinData/image1.png)."""
    with zipfile.ZipFile(str(path)) as z:
        if storage_id not in z.namelist():
            raise_hwp_error(ErrorCode.ATTACHMENT_NOT_FOUND, detail=storage_id)
        with z.open(storage_id) as f:
            data = f.read()
    filename = Path(storage_id).name
    return data, filename, _guess_media_type(filename, data)


def _guess_media_type(filename: str, sample: bytes) -> str:
    """매직바이트 우선 → 확장자 fallback → 기본값."""
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if sample.startswith(b"GIF8"):
        return "image/gif"
    if sample.startswith(b"BM"):
        return "image/bmp"
    if sample.startswith(_OLE_MAGIC):
        return "application/x-ole-storage"
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    return "application/octet-stream"
