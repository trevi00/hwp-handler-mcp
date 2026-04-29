"""extract_metadata MCP 도구."""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, Field

from hwp_mcp.errors import ErrorCode, raise_hwp_error
from hwp_mcp.ir import Format
from hwp_mcp.parsers.detect import detect_magic
from hwp_mcp.parsers.hwp5 import parse_hwp5
from hwp_mcp.parsers.hwpx import parse_hwpx


class MetadataResult(BaseModel):
    format: Format
    title: str | None = None
    author: str | None = None
    last_author: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    company: str | None = None
    section_count: int = 0
    page_count: int | None = None
    raw: dict[str, str] = Field(default_factory=dict)
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


def extract_metadata_impl(path: str, password: str | None = None) -> MetadataResult:
    """extract_metadata MCP 도구의 구현."""
    started = time.perf_counter()
    p = Path(path)

    fmt = detect_magic(p)

    if fmt == Format.HWP5:
        if password is not None:
            raise_hwp_error(
                ErrorCode.PASSWORD_REQUIRED,
                detail="비밀번호 복호화는 Phase B에서 지원 예정",
            )
        doc = parse_hwp5(str(p))
    elif fmt == Format.HWPX:
        doc = parse_hwpx(str(p))
    else:
        raise_hwp_error(
            ErrorCode.UNSUPPORTED_VERSION, detail=f"미지원 포맷: {fmt}"
        )

    md = doc.metadata
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return MetadataResult(
        format=doc.format,
        title=md.title,
        author=md.author,
        last_author=md.last_author,
        created_at=md.created_at.isoformat() if md.created_at else None,
        modified_at=md.modified_at.isoformat() if md.modified_at else None,
        company=md.company,
        section_count=md.section_count,
        page_count=md.page_count,
        raw={k: str(v) for k, v in md.raw.items()},
        elapsed_ms=elapsed_ms,
    )
