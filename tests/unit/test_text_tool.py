from __future__ import annotations

from hwp_mcp.ir import (
    BreakKind,
    Document,
    Format,
    InlineKind,
    InlineObject,
    Metadata,
    Paragraph,
    Run,
    Section,
    SecurityFlags,
    TablePayload,
)
from hwp_mcp.tools.text import document_to_text


def _doc_with_paragraphs(paragraphs: tuple[Paragraph, ...]) -> Document:
    return Document(
        format=Format.HWP5,
        version="5.1.0.0",
        flags=SecurityFlags(),
        metadata=Metadata(),
        sections=(Section(index=0, paragraphs=paragraphs),),
    )


def test_document_to_text_simple() -> None:
    doc = _doc_with_paragraphs(
        (
            Paragraph(index=0, runs=(Run(text="첫 단락"),)),
            Paragraph(index=1, runs=(Run(text="두 번째 단락"),)),
        )
    )
    assert document_to_text(doc) == "첫 단락\n두 번째 단락"


def test_document_to_text_empty_paragraph_creates_blank_line() -> None:
    doc = _doc_with_paragraphs(
        (
            Paragraph(index=0, runs=(Run(text="A"),)),
            Paragraph(index=1, runs=()),
            Paragraph(index=2, runs=(Run(text="B"),)),
        )
    )
    assert document_to_text(doc) == "A\n\nB"


def test_document_to_text_table_placeholder_default() -> None:
    table = TablePayload(rows=2, cols=2)
    para = Paragraph(
        index=0,
        runs=(Run(text="앞", inline_marker=0), Run(text=" 뒤")),
        inline_objects=(InlineObject(kind=InlineKind.TABLE, ref="t0", payload=table),),
    )
    result = document_to_text(_doc_with_paragraphs((para,)))
    assert "[표 1]" in result
    assert "앞" in result
    assert "뒤" in result


def test_document_to_text_table_inline_markdown() -> None:
    from hwp_mcp.ir import Cell

    cells = (
        (
            Cell(row=0, col=0, paragraphs=(Paragraph(index=0, runs=(Run(text="A"),)),)),
            Cell(row=0, col=1, paragraphs=(Paragraph(index=0, runs=(Run(text="B"),)),)),
        ),
        (
            Cell(row=1, col=0, paragraphs=(Paragraph(index=0, runs=(Run(text="C"),)),)),
            Cell(row=1, col=1, paragraphs=(Paragraph(index=0, runs=(Run(text="D"),)),)),
        ),
    )
    table = TablePayload(rows=2, cols=2, cells=cells)
    para = Paragraph(
        index=0,
        runs=(Run(text="", inline_marker=0),),
        inline_objects=(InlineObject(kind=InlineKind.TABLE, ref="t0", payload=table),),
    )
    result = document_to_text(_doc_with_paragraphs((para,)), include_tables=True)
    assert "| A | B |" in result
    assert "| C | D |" in result
    assert "|---|---|" in result


def test_document_to_text_page_break() -> None:
    doc = _doc_with_paragraphs(
        (
            Paragraph(index=0, runs=(Run(text="A"),), break_after=BreakKind.PAGE),
            Paragraph(index=1, runs=(Run(text="B"),)),
        )
    )
    result = document_to_text(doc)
    assert "\f" in result
    assert result.startswith("A")
    assert result.endswith("B")
