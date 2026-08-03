"""extract_tables MCP 도구.

HWPX는 python-hwpx의 ``get_table_map()`` 에 위임한다. HWP5 바이너리의 인라인
표 분해는 아직 미지원이며, 그 사실을 warnings로 명시한다 (조용히 0개를 반환하지
않는다).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import Format
from hwp_handler_mcp.parsers.detect import detect_magic

log = logging.getLogger(__name__)


class TableExtract(BaseModel):
    section_index: int
    table_index: int
    rows: int
    cols: int
    cells: list[list[str]]
    has_merged_cells: bool = False
    caption: str | None = None
    header_text: str | None = None


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
            detail="암호화 문서 복호화는 아직 지원하지 않습니다",
        )

    warnings: list[str] = []
    tables: list[TableExtract] = []

    if fmt == Format.HWPX:
        tables = _extract_hwpx_tables(str(p), section_index)
    elif fmt == Format.HWP5:
        warnings.append(
            "HWP5(.hwp) 바이너리의 표 분해는 아직 지원하지 않습니다. "
            "표를 구조로 얻으려면 HWPX(.hwpx)로 저장한 뒤 다시 시도하세요. "
            "본문 텍스트는 extract_text로 정상 추출됩니다."
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
    """python-hwpx ``get_table_map()`` 위임.

    반환 구조 (python-hwpx 5.6 실측)::

        {"tables": [{"table_index", "paragraph_index", "rows", "cols",
                     "caption_text", "header_text",
                     "cells": [{"row", "col", "text"}, ...]}]}

    ``paragraph_index`` 는 **문서 전역** 인덱스라, 섹션 귀속은 섹션별 문단 수를
    누적해 역산한다.
    """
    from hwpx import HwpxDocument

    doc = HwpxDocument.open(path)
    try:
        para_to_section = _build_paragraph_section_map(doc)
        entries = _as_table_entries(doc.get_table_map())

        out: list[TableExtract] = []
        for entry in entries:
            para_idx = _get(entry, "paragraph_index", -1)
            sec_idx = para_to_section.get(para_idx, 0)
            if section_filter is not None and sec_idx != section_filter:
                continue

            rows = int(_get(entry, "rows", 0) or 0)
            cols = int(_get(entry, "cols", 0) or 0)
            cell_entries = list(_get(entry, "cells", []) or [])
            grid = _build_grid(cell_entries, rows, cols)

            out.append(
                TableExtract(
                    section_index=sec_idx,
                    table_index=int(_get(entry, "table_index", len(out)) or 0),
                    rows=rows,
                    cols=cols,
                    cells=grid,
                    # 셀 엔트리 수가 rows*cols 보다 적으면 병합된 셀이 있다.
                    has_merged_cells=bool(rows and cols and len(cell_entries) < rows * cols),
                    caption=_nonempty(_get(entry, "caption_text", None)),
                    header_text=_nonempty(_get(entry, "header_text", None)),
                )
            )
        return out
    finally:
        doc.close()


def _build_paragraph_section_map(doc: Any) -> dict[int, int]:
    """문서 전역 문단 인덱스 → 섹션 인덱스."""
    mapping: dict[int, int] = {}
    cursor = 0
    for sec_idx, section in enumerate(doc.sections):
        for _ in section.paragraphs:
            mapping[cursor] = sec_idx
            cursor += 1
    return mapping


def _as_table_entries(table_map: Any) -> list[Any]:
    """``get_table_map()`` 반환에서 표 엔트리 리스트를 꺼낸다.

    dict(``{"tables": [...]}``)와 속성 접근(``.tables``) 양쪽을 받는다.
    """
    if isinstance(table_map, dict):
        return list(table_map.get("tables", []) or [])
    tables_attr = getattr(table_map, "tables", None)
    if tables_attr is not None:
        return list(tables_attr)
    if isinstance(table_map, list):
        return list(table_map)
    log.warning("get_table_map() 반환 형태를 해석할 수 없음: %s", type(table_map).__name__)
    return []


def _get(entry: Any, key: str, default: Any) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _build_grid(cell_entries: list[Any], rows: int, cols: int) -> list[list[str]]:
    """평면 셀 리스트를 rows×cols 2차원 배열로 재구성."""
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in cell_entries:
        r = int(_get(cell, "row", 0) or 0)
        c = int(_get(cell, "col", 0) or 0)
        if 0 <= r < rows and 0 <= c < cols:
            grid[r][c] = str(_get(cell, "text", "") or "")
        else:
            log.debug("표 범위 밖 셀 무시: row=%s col=%s (rows=%s cols=%s)", r, c, rows, cols)
    return grid


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
