"""extract_text MCP 도구."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, Field

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import BreakKind, Document, Format, InlineKind, TablePayload
from hwp_handler_mcp.parsers.detect import detect_magic
from hwp_handler_mcp.parsers.hwp5 import parse_hwp5
from hwp_handler_mcp.parsers.hwpx import parse_hwpx


class ExtractText(BaseModel):
    text: str
    char_count: int
    total_char_count: int
    truncated: bool
    next_offset: int | None = None
    format: Format
    section_count: int
    page_count: int | None = None
    partial: bool = False
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


def extract_text_impl(
    path: str,
    password: str | None = None,
    max_chars: int = 100_000,
    offset: int = 0,
    include_tables: bool = False,
    include_images: bool = False,
) -> ExtractText:
    """extract_text MCP 도구의 구현.

    Args:
        path: HWP/HWPX 파일 절대경로.
        password: 내부 가드용. 암호화 문서는 지원하지 않으며 값을 주면 거부한다.
        max_chars: 결과 텍스트 최대 문자 수.
        offset: 페이징 오프셋.
        include_tables: True면 표를 Markdown으로 인라인. False면 [표 N] placeholder.
        include_images: True면 이미지 위치에 [이미지] 마커.
    """
    started = time.perf_counter()
    p = Path(path)

    if max_chars < 1:
        raise_hwp_error(ErrorCode.OFFSET_OUT_OF_RANGE, detail="max_chars must be >= 1")
    if offset < 0:
        raise_hwp_error(ErrorCode.OFFSET_OUT_OF_RANGE, detail="offset must be >= 0")

    fmt = detect_magic(p)
    doc = _dispatch_parse(fmt, str(p), password)

    full_text = document_to_text(doc, include_tables=include_tables, include_images=include_images)
    total = len(full_text)

    if offset > total:
        raise_hwp_error(
            ErrorCode.OFFSET_OUT_OF_RANGE,
            extra={"offset": offset, "total": total},
        )

    chunk = full_text[offset : offset + max_chars]
    end = offset + len(chunk)
    next_offset = end if end < total else None

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    warnings: list[str] = []
    if doc.partial:
        warnings.append("일부 섹션 파싱 실패 — 가능한 만큼만 반환")

    return ExtractText(
        text=chunk,
        char_count=len(chunk),
        total_char_count=total,
        truncated=next_offset is not None,
        next_offset=next_offset,
        format=doc.format,
        section_count=len(doc.sections),
        page_count=doc.metadata.page_count,
        partial=doc.partial,
        elapsed_ms=elapsed_ms,
        warnings=warnings,
    )


def _dispatch_parse(fmt: Format, path: str, password: str | None) -> Document:
    """포맷별 파서 디스패치."""
    if fmt == Format.HWP5:
        if password is not None:
            raise_hwp_error(
                ErrorCode.PASSWORD_REQUIRED,
                detail="암호화된 문서는 지원하지 않습니다",
            )
        return parse_hwp5(path)
    if fmt == Format.HWPX:
        return parse_hwpx(path)
    if fmt == Format.HWP3:
        raise_hwp_error(
            ErrorCode.UNSUPPORTED_VERSION,
            detail="HWP 3.x(한글 97/98)는 지원하지 않습니다",
        )
    raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"포맷 인식 실패: {fmt}")
    raise AssertionError("unreachable")  # ruff RET503


def document_to_text(
    doc: Document,
    *,
    include_tables: bool = False,
    include_images: bool = False,
    table_placeholder: str = "[표 {n}]",
) -> str:
    """IR Document → 평문 텍스트 (FORMAT-IR.md §5)."""
    parts: list[str] = []
    table_counter = 0
    for section in doc.sections:
        for para in section.paragraphs:
            line: list[str] = []
            for run in para.runs:
                line.append(run.text)
                if run.inline_marker is not None and run.inline_marker < len(para.inline_objects):
                    obj = para.inline_objects[run.inline_marker]
                    if obj.kind == InlineKind.TABLE:
                        if include_tables and isinstance(obj.payload, TablePayload):
                            line.append(_table_to_markdown(obj.payload))
                        else:
                            table_counter += 1
                            line.append(table_placeholder.format(n=table_counter))
                    elif obj.kind == InlineKind.IMAGE and include_images:
                        line.append("[이미지]")
            parts.append("".join(line))
            if para.break_after == BreakKind.PAGE:
                parts.append("\f")
    return "\n".join(parts)


def _table_to_markdown(table: TablePayload) -> str:
    """표 → Markdown 표 (간단). 병합셀은 placeholder 텍스트만 반영."""
    if not table.cells:
        return ""
    rows: list[str] = []
    for row_idx, row in enumerate(table.cells):
        cell_texts = [_cell_to_text(c) for c in row]
        rows.append("| " + " | ".join(cell_texts) + " |")
        if row_idx == 0:
            rows.append("|" + "|".join(["---"] * len(row)) + "|")
    return "\n" + "\n".join(rows) + "\n"


def _cell_to_text(cell) -> str:  # type: ignore[no-untyped-def]
    """Cell IR → 단일 라인 텍스트 (셀 안 단락은 공백으로 join)."""
    return " ".join("".join(run.text for run in para.runs) for para in cell.paragraphs)
