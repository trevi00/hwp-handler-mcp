from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Format(StrEnum):
    HWP5 = "hwp5"
    HWPX = "hwpx"
    HWP3 = "hwp3"


class BreakKind(StrEnum):
    NONE = "none"
    PAGE = "page"
    COLUMN = "column"
    SECTION = "section"


class InlineKind(StrEnum):
    TABLE = "table"
    IMAGE = "image"
    EQUATION = "equation"
    FIELD = "field"
    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"
    OLE = "ole"
    CHART = "chart"
    SHAPE = "shape"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SecurityFlags:
    compressed: bool = False
    encrypted: bool = False
    distribution: bool = False
    drm: bool = False
    digital_signature: bool = False
    public_key_encrypted: bool = False
    script: bool = False


@dataclass(frozen=True, slots=True)
class Metadata:
    title: str | None = None
    author: str | None = None
    last_author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    company: str | None = None
    section_count: int = 0
    page_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageDef:
    width: int | None = None
    height: int | None = None
    margins: dict[str, int] = field(default_factory=dict)
    columns: int = 1


@dataclass(frozen=True, slots=True)
class Run:
    text: str
    char_style: str | None = None
    inline_marker: int | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    paragraphs: tuple[Paragraph, ...] = ()


@dataclass(frozen=True, slots=True)
class TablePayload:
    rows: int
    cols: int
    cells: tuple[tuple[Cell, ...], ...] = ()
    has_merged: bool = False
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class ImagePayload:
    attachment_ref: str | None = None
    width_emu: int | None = None
    height_emu: int | None = None


@dataclass(frozen=True, slots=True)
class FieldPayload:
    field_type: str
    value: str | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class FootnotePayload:
    number: int
    paragraphs: tuple[Paragraph, ...] = ()


_PayloadUnion = TablePayload | ImagePayload | FieldPayload | FootnotePayload | None


@dataclass(frozen=True, slots=True)
class InlineObject:
    kind: InlineKind
    ref: str
    payload: _PayloadUnion = None


@dataclass(frozen=True, slots=True)
class Paragraph:
    index: int
    style_name: str | None = None
    runs: tuple[Run, ...] = ()
    inline_objects: tuple[InlineObject, ...] = ()
    break_after: BreakKind = BreakKind.NONE
    raw_attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Section:
    index: int
    page_def: PageDef | None = None
    paragraphs: tuple[Paragraph, ...] = ()


@dataclass(frozen=True, slots=True)
class Attachment:
    id: str
    filename: str
    media_type: str
    size_bytes: int
    data: bytes | None = None
    source_format: Format = Format.HWP5


@dataclass(frozen=True, slots=True)
class Document:
    format: Format
    version: str
    flags: SecurityFlags
    metadata: Metadata
    sections: tuple[Section, ...]
    attachments: tuple[Attachment, ...] = ()
    partial: bool = False
