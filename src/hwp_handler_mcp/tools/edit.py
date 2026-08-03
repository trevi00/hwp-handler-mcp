"""HWPX 쓰기 도구 (생성 / 치환 / 양식 채우기 / 머리말·꼬리말 / Markdown 변환).

전부 python-hwpx 에 위임한다. **쓰기는 HWPX 전용**이다 — HWP5(.hwp) 바이너리
저작은 순수 Python 구현이 없으므로 명시적으로 거부한다 (조용히 실패하지 않는다).

안전 규칙:

- 출력 경로가 이미 존재하면 ``overwrite=True`` 없이는 거부한다. 에이전트가
  운전하는 도구라 덮어쓰기는 되돌릴 수 없다.
- ``output_path`` 를 생략하면 입력 파일을 제자리 수정한다 — 이 경우도 명시적
  ``in_place=True`` 를 요구한다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import Format
from hwp_handler_mcp.parsers.detect import detect_magic


class WriteResult(BaseModel):
    output_path: str
    bytes_written: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


class ReplaceResult(BaseModel):
    output_path: str
    replaced_count: int
    per_pattern: dict[str, int]
    bytes_written: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


class FillEntry(BaseModel):
    path: str
    table_index: int | None = None
    row: int | None = None
    col: int | None = None
    value: str | None = None
    reason: str | None = None


class FillResult(BaseModel):
    output_path: str
    applied: list[FillEntry]
    failed: list[FillEntry]
    applied_count: int
    failed_count: int
    bytes_written: int
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


class MarkdownResult(BaseModel):
    markdown: str
    char_count: int
    format: Format
    elapsed_ms: int
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 공통 가드
# --------------------------------------------------------------------------


def _require_hwpx(path: Path) -> None:
    """쓰기 대상이 HWPX인지 확인. HWP5면 명시적으로 거부."""
    fmt = detect_magic(path)
    if fmt == Format.HWPX:
        return
    if fmt == Format.HWP5:
        raise_hwp_error(
            ErrorCode.UNSUPPORTED_VERSION,
            detail=(
                "HWP5(.hwp) 바이너리 쓰기는 지원하지 않습니다. "
                "한글에서 .hwpx로 저장한 뒤 다시 시도하세요"
            ),
        )
    raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"쓰기 미지원 포맷: {fmt}")


def _resolve_output(
    source: Path | None,
    output_path: str | None,
    *,
    overwrite: bool,
    in_place: bool,
) -> Path:
    """출력 경로 결정 + 덮어쓰기 가드."""
    if output_path is None:
        if source is None:
            raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="output_path가 필요합니다")
        if not in_place:
            raise_hwp_error(
                ErrorCode.INVALID_FORMAT,
                detail=(
                    "output_path를 생략하려면 in_place=True를 명시해야 합니다 (원본이 덮어써집니다)"
                ),
            )
        return source

    target = Path(output_path)
    if target.exists() and not overwrite:
        raise_hwp_error(
            ErrorCode.INVALID_FORMAT,
            detail=(
                f"출력 파일이 이미 존재합니다: {target}. 덮어쓰려면 overwrite=True를 지정하세요"
            ),
        )
    if target.parent and not target.parent.exists():
        raise_hwp_error(ErrorCode.FILE_NOT_FOUND, detail=f"출력 디렉터리 없음: {target.parent}")
    return target


def _save(doc: Any, target: Path) -> int:
    """python-hwpx 문서를 저장하고 기록된 바이트 수를 반환."""
    saver = getattr(doc, "save_to_path", None) or doc.save
    saver(str(target))
    return target.stat().st_size


def _open_hwpx(path: Path) -> Any:
    from hwpx import HwpxDocument

    try:
        return HwpxDocument.open(str(path))
    except Exception as exc:  # noqa: BLE001 — 라이브러리 경계
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"HWPX 열기 실패: {exc}")


# --------------------------------------------------------------------------
# 도구 구현
# --------------------------------------------------------------------------


def create_document_impl(
    output_path: str,
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
    header_text: str | None = None,
    footer_text: str | None = None,
    overwrite: bool = False,
) -> WriteResult:
    """새 HWPX 문서를 만든다.

    문단을 먼저 쓰고, ``tables`` 의 각 2차원 배열을 순서대로 표로 추가한다.
    """
    started = time.perf_counter()
    from hwpx import HwpxDocument

    target = _resolve_output(None, output_path, overwrite=overwrite, in_place=False)

    doc = HwpxDocument.new()
    for text in paragraphs or []:
        doc.add_paragraph(text)

    warnings: list[str] = []
    for grid in tables or []:
        rows = len(grid)
        cols = max((len(r) for r in grid), default=0)
        if rows == 0 or cols == 0:
            warnings.append("빈 표 정의는 건너뜀")
            continue
        table = doc.add_table(rows=rows, cols=cols)
        _write_grid(table, grid, warnings)

    if header_text is not None:
        doc.set_header_text(header_text)
    if footer_text is not None:
        doc.set_footer_text(footer_text)

    written = _save(doc, target)
    return WriteResult(
        output_path=str(target),
        bytes_written=written,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )


def _write_grid(table: Any, grid: list[list[str]], warnings: list[str]) -> None:
    """2차원 문자열 배열을 표 셀에 기록."""
    for r, row_obj in enumerate(table.rows):
        if r >= len(grid):
            break
        for c, cell in enumerate(row_obj.cells):
            if c >= len(grid[r]):
                break
            value = str(grid[r][c])
            setter = getattr(cell, "set_text", None)
            if setter is None:  # pragma: no cover — API 변경 감지용
                warnings.append("셀 쓰기 API(set_text)를 찾을 수 없어 일부 셀을 건너뜀")
                return
            setter(value)


def replace_text_impl(
    path: str,
    replacements: dict[str, str],
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> ReplaceResult:
    """본문 텍스트를 일괄 치환한다 (템플릿 채우기)."""
    started = time.perf_counter()
    source = Path(path)
    _require_hwpx(source)
    target = _resolve_output(source, output_path, overwrite=overwrite, in_place=in_place)

    if not replacements:
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="replacements가 비어 있습니다")

    doc = _open_hwpx(source)
    per_pattern: dict[str, int] = {}
    try:
        for old, new in replacements.items():
            count = doc.replace_text_in_runs(old, new)
            per_pattern[old] = int(count or 0)
        written = _save(doc, target)
    finally:
        doc.close()

    total = sum(per_pattern.values())
    warnings: list[str] = []
    missed = [k for k, v in per_pattern.items() if v == 0]
    if missed:
        warnings.append(f"문서에서 찾지 못한 패턴: {', '.join(missed)}")

    return ReplaceResult(
        output_path=str(target),
        replaced_count=total,
        per_pattern=per_pattern,
        bytes_written=written,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )


def fill_form_impl(
    path: str,
    mappings: dict[str, str],
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> FillResult:
    """표 라벨을 기준으로 인접 셀에 값을 채운다.

    키는 ``"라벨 > 방향"`` 경로다 (방향: ``right`` / ``left`` / ``below`` / ``above``).
    예: ``{"성명 > right": "김철수"}``.
    """
    started = time.perf_counter()
    source = Path(path)
    _require_hwpx(source)
    target = _resolve_output(source, output_path, overwrite=overwrite, in_place=in_place)

    if not mappings:
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail="mappings가 비어 있습니다")

    doc = _open_hwpx(source)
    try:
        result = doc.fill_by_path(mappings)
        written = _save(doc, target)
    finally:
        doc.close()

    applied = [_to_fill_entry(e) for e in _dget(result, "applied", []) or []]
    failed = [_to_fill_entry(e) for e in _dget(result, "failed", []) or []]

    warnings: list[str] = []
    if failed:
        warnings.append(
            f"{len(failed)}개 경로를 문서에서 찾지 못했습니다. "
            "라벨 텍스트가 표 셀에 정확히 존재하는지 확인하세요"
        )

    return FillResult(
        output_path=str(target),
        applied=applied,
        failed=failed,
        applied_count=len(applied),
        failed_count=len(failed),
        bytes_written=written,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )


def _dget(obj: Any, key: str, default: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_fill_entry(entry: Any) -> FillEntry:
    return FillEntry(
        path=str(_dget(entry, "path", "")),
        table_index=_dget(entry, "table_index", None),
        row=_dget(entry, "row", None),
        col=_dget(entry, "col", None),
        value=_dget(entry, "value", None),
        reason=_dget(entry, "reason", None),
    )


def set_header_footer_impl(
    path: str,
    header_text: str | None = None,
    footer_text: str | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> WriteResult:
    """머리말/꼬리말을 설정한다. ``None`` 인 쪽은 건드리지 않는다."""
    started = time.perf_counter()
    source = Path(path)
    _require_hwpx(source)
    target = _resolve_output(source, output_path, overwrite=overwrite, in_place=in_place)

    if header_text is None and footer_text is None:
        raise_hwp_error(
            ErrorCode.INVALID_FORMAT,
            detail="header_text 또는 footer_text 중 하나는 필요합니다",
        )

    doc = _open_hwpx(source)
    try:
        if header_text is not None:
            doc.set_header_text(header_text)
        if footer_text is not None:
            doc.set_footer_text(footer_text)
        written = _save(doc, target)
    finally:
        doc.close()

    return WriteResult(
        output_path=str(target),
        bytes_written=written,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


def convert_to_markdown_impl(path: str, include_tables: bool = True) -> MarkdownResult:
    """문서를 Markdown으로 변환한다 (LLM 입력용).

    HWPX는 python-hwpx의 내장 exporter를 쓴다. HWP5는 표 구조 분해가 없으므로
    본문 텍스트를 문단 단위로 옮기고 그 한계를 warnings에 남긴다.
    """
    started = time.perf_counter()
    source = Path(path)
    fmt = detect_magic(source)
    warnings: list[str] = []

    if fmt == Format.HWPX:
        doc = _open_hwpx(source)
        try:
            markdown = doc.export_markdown()
        finally:
            doc.close()
    elif fmt == Format.HWP5:
        from hwp_handler_mcp.parsers.hwp5 import parse_hwp5
        from hwp_handler_mcp.tools.text import document_to_text

        parsed = parse_hwp5(str(source))
        markdown = document_to_text(parsed, include_tables=False)
        warnings.append(
            "HWP5(.hwp)는 표 구조 분해를 지원하지 않아 표가 Markdown 표로 "
            "변환되지 않습니다. 표가 중요하면 .hwpx로 저장한 뒤 다시 시도하세요."
        )
    else:
        raise_hwp_error(ErrorCode.UNSUPPORTED_VERSION, detail=f"미지원 포맷: {fmt}")

    if not include_tables:
        warnings.append("include_tables=False는 HWPX exporter에 전달되지 않습니다")

    return MarkdownResult(
        markdown=markdown,
        char_count=len(markdown),
        format=fmt,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
    )
