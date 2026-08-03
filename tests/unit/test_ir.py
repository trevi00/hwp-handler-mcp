from __future__ import annotations

import dataclasses

import pytest

from hwp_handler_mcp.ir import (
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


def test_document_is_immutable() -> None:
    doc = Document(
        format=Format.HWP5,
        version="5.1.0.0",
        flags=SecurityFlags(),
        metadata=Metadata(),
        sections=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.version = "6.0.0.0"  # type: ignore[misc]


def test_paragraph_with_inline_table() -> None:
    table = TablePayload(rows=2, cols=2)
    para = Paragraph(
        index=0,
        runs=(Run(text="앞 텍스트", inline_marker=0), Run(text=" 뒤 텍스트")),
        inline_objects=(InlineObject(kind=InlineKind.TABLE, ref="table_0", payload=table),),
        break_after=BreakKind.PAGE,
    )
    assert para.runs[0].inline_marker == 0
    assert para.inline_objects[0].kind == InlineKind.TABLE
    assert para.break_after == BreakKind.PAGE


def test_security_flags_default_all_false() -> None:
    flags = SecurityFlags()
    assert not flags.compressed
    assert not flags.encrypted
    assert not flags.drm


def test_section_paragraph_count() -> None:
    s = Section(
        index=0,
        paragraphs=(Paragraph(index=0), Paragraph(index=1), Paragraph(index=2)),
    )
    assert len(s.paragraphs) == 3
