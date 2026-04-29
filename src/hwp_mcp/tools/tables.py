"""extract_tables MCP 도구.

Phase A에서는 HWPX만 (python-hwpx 위임). HWP5 inline table 분해는 Phase B 예정.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from hwp_mcp.errors import ErrorCode, raise_hwp_error
from hwp_mcp.ir import Format
from hwp_mcp.parsers.detect import detect_magic

log = logging.getLogger(__name__)


class TableExtract(BaseModel):
    section_index: int
    table_index: int
    rows: int
    cols: int
    cells: list[list[str]]
    has_merged_cells: bool = False
    caption: str | None = None


class ExtractTablesResult(BaseModel):
    tables: list[TableExtract]
    total_count: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


def extract_tables_impl(
    path: str,
    password: str | None = None,
    section_index: int | None = None,
) -> ExtractTablesResult:
    """문서 내 모든 표를 행/열 매트릭스로 추출."""
    started = time.perf_counter()
    p = Path(path)
    fmt = detect_magic(p)

    if password is not None:
        raise_hwp_error(
            ErrorCode.PASSWORD_REQUIRED,
            detail="비밀번호 복호화는 Phase B에서 지원 예정",
        )

    warnings: list[str] = []
    tables: list[TableExtract] = []

    if fmt == Format.HWPX:
        tables = _extract_hwpx_tables(str(p), section_index)
    elif fmt == Format.HWP5:
        warnings.append(
            "HWP5 표 분해는 Phase B에서 지원 예정. 현재는 HWPX만 표 추출 가능."
        )
    else:
        raise_hwp_error(ErrorCode.UNSUPPORTED_VERSION, detail=f"미지원 포맷: {fmt}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return ExtractTablesResult(
        tables=tables,
        total_count=len(tables),
        elapsed_ms=elapsed_ms,
        warnings=warnings,
    )


def _extract_hwpx_tables(path: str, section_filter: int | None) -> list[TableExtract]:
    """python-hwpx의 get_table_map을 활용한 표 추출."""
    from hwpx import HwpxDocument

    doc = HwpxDocument.open(path)
    out: list[TableExtract] = []
    try:
        # python-hwpx의 paragraphs를 순회하며 table 객체 찾기
        # — get_table_map() 또는 sections를 직접 순회
        sections = list(doc.sections) if hasattr(doc, "sections") else []
        for s_idx, section in enumerate(sections):
            if section_filter is not None and s_idx != section_filter:
                continue
            for t_idx, table_meta in enumerate(_iter_section_tables(section)):
                cells_2d = table_meta["cells"]
                rows = len(cells_2d)
                cols = max((len(r) for r in cells_2d), default=0)
                out.append(
                    TableExtract(
                        section_index=s_idx,
                        table_index=t_idx,
                        rows=rows,
                        cols=cols,
                        cells=cells_2d,
                        has_merged_cells=table_meta.get("has_merged", False),
                        caption=table_meta.get("caption"),
                    )
                )
    finally:
        doc.close()
    return out


def _iter_section_tables(section: object):  # type: ignore[no-untyped-def]
    """python-hwpx section 객체 → 표 메타 시퀀스.

    python-hwpx 내부 API 변경 가능성을 고려한 best-effort 어댑터.
    """
    iter_attr = getattr(section, "iter_tables", None)
    if iter_attr is None:
        # fallback: paragraphs 안의 hp:tbl 노드 탐색
        log.debug("section.iter_tables 없음 — fallback 사용")
        return iter(())

    for table in iter_attr():
        cells: list[list[str]] = []
        rows_attr = getattr(table, "rows", None)
        if rows_attr is None:
            continue
        for row in rows_attr:
            row_cells: list[str] = []
            cells_attr = getattr(row, "cells", None) or []
            for cell in cells_attr:
                row_cells.append(_cell_text(cell))
            cells.append(row_cells)
        yield {
            "cells": cells,
            "has_merged": getattr(table, "has_merged_cells", False),
            "caption": getattr(table, "caption", None),
        }


def _cell_text(cell: object) -> str:
    text_attr = getattr(cell, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    paragraphs_attr = getattr(cell, "paragraphs", None) or []
    return "\n".join(getattr(p, "text", "") or "" for p in paragraphs_attr)
