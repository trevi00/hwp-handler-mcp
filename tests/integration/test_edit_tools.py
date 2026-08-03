"""쓰기 도구 왕복 검증.

문서를 만들거나 고친 뒤 **우리 파서로 되읽어** 확인한다. 라이브러리 반환값만
믿지 않는다 — 저장까지 끝난 파일이 실제로 그 내용을 담고 있는지가 계약이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwp_handler_mcp._compat import McpError
from hwp_handler_mcp.ir import Format
from hwp_handler_mcp.tools.edit import (
    convert_to_markdown_impl,
    create_document_impl,
    fill_form_impl,
    replace_text_impl,
    set_header_footer_impl,
)
from hwp_handler_mcp.tools.tables import extract_tables_impl
from hwp_handler_mcp.tools.text import extract_text_impl

pytestmark = pytest.mark.integration

REAL_HWP5 = Path(__file__).parent.parent / "fixtures" / "real_hwp5" / "blank.hwp"


@pytest.fixture
def form_document(tmp_path: Path) -> Path:
    """라벨 | 빈칸 구조의 양식 문서."""
    target = tmp_path / "form.hwpx"
    create_document_impl(
        str(target),
        paragraphs=["출장 신청서"],
        tables=[[["성명", ""], ["부서", ""], ["출장지", ""]]],
    )
    return target


# ---------------------------------------------------------------- create


def test_create_document_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "new.hwpx"
    result = create_document_impl(
        str(target),
        paragraphs=["첫 문단입니다.", "둘째 문단입니다."],
        tables=[[["분기", "매출"], ["1Q", "120"]]],
    )
    assert Path(result.output_path).exists()
    assert result.bytes_written > 0

    text = extract_text_impl(str(target))
    assert text.format == Format.HWPX
    assert "첫 문단입니다." in text.text
    assert "둘째 문단입니다." in text.text

    tables = extract_tables_impl(str(target))
    assert tables.total_count == 1
    assert tables.tables[0].cells == [["분기", "매출"], ["1Q", "120"]]


def test_create_document_refuses_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "exists.hwpx"
    create_document_impl(str(target), paragraphs=["원본"])
    with pytest.raises(McpError):
        create_document_impl(str(target), paragraphs=["덮어쓰기 시도"])
    # 원본이 보존되어야 한다
    assert "원본" in extract_text_impl(str(target)).text


def test_create_document_overwrite_allowed(tmp_path: Path) -> None:
    target = tmp_path / "exists.hwpx"
    create_document_impl(str(target), paragraphs=["원본"])
    create_document_impl(str(target), paragraphs=["교체됨"], overwrite=True)
    assert "교체됨" in extract_text_impl(str(target)).text


# ---------------------------------------------------------------- replace


def test_replace_text_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(str(src), paragraphs=["담당자: 홍길동", "연락처: 000"])
    out = tmp_path / "out.hwpx"

    result = replace_text_impl(str(src), replacements={"홍길동": "김철수"}, output_path=str(out))
    assert result.replaced_count == 1
    assert result.per_pattern["홍길동"] == 1

    text = extract_text_impl(str(out)).text
    assert "김철수" in text
    assert "홍길동" not in text
    # 원본은 그대로여야 한다
    assert "홍길동" in extract_text_impl(str(src)).text


def test_replace_text_reports_missing_pattern(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(str(src), paragraphs=["담당자: 홍길동"])
    out = tmp_path / "out.hwpx"
    result = replace_text_impl(str(src), replacements={"없는문자열": "X"}, output_path=str(out))
    assert result.replaced_count == 0
    assert result.warnings, "찾지 못한 패턴은 조용히 넘어가면 안 된다"


def test_replace_text_requires_explicit_in_place(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(str(src), paragraphs=["원본"])
    with pytest.raises(McpError):
        replace_text_impl(str(src), replacements={"원본": "변경"})


# ---------------------------------------------------------------- fill_form


def test_fill_form_by_label(form_document: Path, tmp_path: Path) -> None:
    out = tmp_path / "filled.hwpx"
    result = fill_form_impl(
        str(form_document),
        mappings={
            "성명 > right": "김철수",
            "부서 > right": "개발팀",
            "출장지 > right": "부산",
        },
        output_path=str(out),
    )
    assert result.applied_count == 3
    assert result.failed_count == 0

    cells = extract_tables_impl(str(out)).tables[0].cells
    assert cells == [
        ["성명", "김철수"],
        ["부서", "개발팀"],
        ["출장지", "부산"],
    ]


def test_fill_form_reports_unknown_label(form_document: Path, tmp_path: Path) -> None:
    out = tmp_path / "filled.hwpx"
    result = fill_form_impl(
        str(form_document),
        mappings={"존재하지않는라벨 > right": "값"},
        output_path=str(out),
    )
    assert result.applied_count == 0
    assert result.failed_count == 1
    assert result.warnings


# ---------------------------------------------------------------- header/footer


def test_set_header_footer(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(str(src), paragraphs=["본문"])
    out = tmp_path / "hf.hwpx"
    result = set_header_footer_impl(
        str(src), header_text="머리말", footer_text="꼬리말", output_path=str(out)
    )
    assert Path(result.output_path).exists()
    assert result.bytes_written > 0


def test_set_header_footer_requires_one_argument(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(str(src), paragraphs=["본문"])
    with pytest.raises(McpError):
        set_header_footer_impl(str(src), output_path=str(tmp_path / "x.hwpx"))


# ---------------------------------------------------------------- markdown


def test_convert_to_markdown_hwpx_includes_table(tmp_path: Path) -> None:
    src = tmp_path / "src.hwpx"
    create_document_impl(
        str(src),
        paragraphs=["보고서"],
        tables=[[["항목", "값"], ["매출", "120"]]],
    )
    result = convert_to_markdown_impl(str(src))
    assert result.format == Format.HWPX
    assert "보고서" in result.markdown
    assert "|" in result.markdown, "HWPX 표는 Markdown 표로 변환되어야 한다"
    assert "매출" in result.markdown


def test_convert_to_markdown_hwp5_warns_about_tables() -> None:
    """HWP5도 변환은 되지만 표 한계를 알려야 한다."""
    result = convert_to_markdown_impl(str(REAL_HWP5))
    assert result.format == Format.HWP5
    assert result.warnings


# ---------------------------------------------------------------- 포맷 가드


def test_write_tools_reject_hwp5() -> None:
    """.hwp 바이너리 쓰기는 조용히 실패하지 않고 명시적으로 거부한다."""
    with pytest.raises(McpError):
        replace_text_impl(str(REAL_HWP5), replacements={"a": "b"}, in_place=True)
    with pytest.raises(McpError):
        fill_form_impl(str(REAL_HWP5), mappings={"a > right": "b"}, in_place=True)
    with pytest.raises(McpError):
        set_header_footer_impl(str(REAL_HWP5), header_text="x", in_place=True)
