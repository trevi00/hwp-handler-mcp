# HWP 통합 내부 표현 (IR) 설계

작성일: 2026-04-29
근거: `.planning/research/{RHWP-HWP5-PARSER, RHWP-HWPX-PARSER, RHWP-CRYPTO, PYTHON-OSS}.md`

> **목표**: HWP5(바이너리) / HWPX(XML) / HWP3(구형)의 서로 다른 표현을 **단일 IR**로 모아, MCP tool 레이어가 포맷 차이를 몰라도 되게 한다.

---

## 1. 설계 원칙

| 원칙 | 적용 |
|---|---|
| **단방향 의존**: parsers → IR, tools → IR | IR은 누구도 import 안 함 |
| **불변(immutable)** | `frozen=True` dataclass / pydantic `model_config = {"frozen": True}` |
| **포맷 중립** | "단락"·"표"·"이미지" 같은 공통 어휘만. HWP 전용 용어(secd, cold)는 raw_attrs에 보관 |
| **부분 파싱 친화** | 일부 섹션 실패해도 가능한 만큼만 채워 반환 + `partial=True` |
| **타입 강제** | `from __future__ import annotations` + `TYPE_CHECKING` |

---

## 2. IR 트리

```
Document
├── format: Format            (hwp5 | hwpx | hwp3)
├── version: str              ("5.1.0.0", "HWPX-2024" 등)
├── flags: SecurityFlags
├── metadata: Metadata
├── sections: list[Section]
├── attachments: list[Attachment]
└── partial: bool             (일부만 파싱됐는지)

Section
├── index: int                (0부터)
├── page_def: PageDef | None
└── paragraphs: list[Paragraph]

Paragraph
├── index: int                (섹션 내)
├── style_name: str | None
├── runs: list[Run]
├── inline_objects: list[InlineObject]   (표/이미지/수식/필드)
├── break_after: BreakKind    (None | Page | Column | Section)
└── raw_attrs: dict[str, Any] (포맷별 보존 — 디버그용)

Run
├── text: str                 (제어문자 제외, 일반 텍스트만)
├── char_style: str | None
└── inline_marker: int | None (인라인 객체 위치 마커. inline_objects[N] 참조)

InlineObject
├── kind: InlineKind          (Table | Image | Equation | Field | Footnote | ...)
├── ref: str                  ("table_0_0", "image_1" 등 고유 ID)
└── payload: TablePayload | ImagePayload | ... (Union)

Table = TablePayload
├── rows: int
├── cols: int
├── cells: list[list[Cell]]
├── has_merged: bool
└── caption: str | None

Cell
├── row: int
├── col: int
├── row_span: int             (default 1)
├── col_span: int             (default 1)
└── paragraphs: list[Paragraph]   (재귀 — 셀 안에 또 단락 트리)

Image = ImagePayload
├── attachment_ref: str | None    (Attachment.id 참조)
├── width_emu: int | None
└── height_emu: int | None

Attachment
├── id: str                  ("BIN0001" 또는 HWPX BinData href)
├── filename: str
├── media_type: str          ("image/png", "application/octet-stream")
├── size_bytes: int
├── data: bytes | None       (메모리 부담 시 None — 별도 호출로 로드)
└── source_format: Format

Metadata
├── title: str | None
├── author: str | None
├── last_author: str | None
├── created_at: datetime | None
├── modified_at: datetime | None
├── company: str | None
├── section_count: int
├── page_count: int | None
└── raw: dict[str, Any]      (파서가 더 뽑아낸 키-값 보존)

SecurityFlags
├── compressed: bool
├── encrypted: bool
├── distribution: bool       (한컴 ViewText 보호본)
├── drm: bool
├── digital_signature: bool
├── public_key_encrypted: bool
└── script: bool

PageDef                      (옵션, 렌더링용 정보)
├── width: int | None        (HWPUNIT)
├── height: int | None
├── margins: dict[str, int]  (left/right/top/bottom/header/footer)
└── columns: int             (기본 1)
```

---

## 3. dataclass 정의 (`src/hwp_mcp/ir/document.py`)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Union


class Format(str, Enum):
    HWP5 = "hwp5"
    HWPX = "hwpx"
    HWP3 = "hwp3"


class BreakKind(str, Enum):
    NONE = "none"
    PAGE = "page"
    COLUMN = "column"
    SECTION = "section"


class InlineKind(str, Enum):
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
    inline_marker: int | None = None  # inline_objects 인덱스


@dataclass(frozen=True, slots=True)
class Cell:
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    paragraphs: tuple["Paragraph", ...] = ()


@dataclass(frozen=True, slots=True)
class TablePayload:
    rows: int
    cols: int
    cells: tuple[tuple[Cell, ...], ...] = ()  # cells[row][col]
    has_merged: bool = False
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class ImagePayload:
    attachment_ref: str | None = None
    width_emu: int | None = None
    height_emu: int | None = None


@dataclass(frozen=True, slots=True)
class FieldPayload:
    field_type: str  # "hyperlink" | "bookmark" | "date" | ...
    value: str | None = None
    target: str | None = None  # 하이퍼링크 URL 등


@dataclass(frozen=True, slots=True)
class FootnotePayload:
    number: int
    paragraphs: tuple["Paragraph", ...] = ()


@dataclass(frozen=True, slots=True)
class InlineObject:
    kind: InlineKind
    ref: str  # 고유 ID (예: "table_0_0", "image_1")
    payload: Union[
        TablePayload, ImagePayload, FieldPayload, FootnotePayload, None
    ] = None


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
    data: bytes | None = None  # None이면 lazy load
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
```

---

## 4. 포맷별 매핑

### 4.1 HWP5 → IR

| HWP5 요소 | IR 매핑 |
|---|---|
| `FileHeader` flags 비트 (`header.rs:74-92`) | `SecurityFlags` 비트 그대로 |
| `FileHeader` major.minor.build.revision | `Document.version = f"{major}.{minor}.{build}.{revision}"` |
| `DocInfo > HWPTAG_DOCUMENT_PROPERTIES` (0x010) | `Metadata.section_count` (page_count는 직접 계산 X) |
| `DocInfo > HWPTAG_BIN_DATA` (0x012) | `Document.attachments[]` (storage_id → `Attachment.id = f"BIN{id:04X}"`) |
| `DocInfo > HWPTAG_STYLE` (0x01A) | `Paragraph.style_name` (이름만) |
| `BodyText/Section{N}` 1개 = 1 `Section` | `sections[N]` |
| `HWPTAG_PARA_HEADER` (0x42) | 새 `Paragraph` 시작 |
| `HWPTAG_PARA_TEXT` (0x43) | `Paragraph.runs` 채움 (control 문자 처리는 `decode_para_text`) |
| `HWPTAG_CTRL_HEADER` (0x47) ctrl_id == "tbl " | `InlineObject(kind=TABLE)` |
| `HWPTAG_CTRL_HEADER` ctrl_id == "secd" | `Section.page_def` 채움 |
| 0x0003/0x0004 (FIELD_BEGIN/END) | `InlineObject(kind=FIELD)` |
| `PARA_HEADER.breakType` 비트 | `Paragraph.break_after` |
| 메타데이터 (작성자/제목) | rhwp 미추출 → `hwp-extract --extract-meta` 결과 활용 |

### 4.2 HWPX → IR

| HWPX 요소 | IR 매핑 |
|---|---|
| `Contents/content.hpf` `<opf:metadata>` | `Metadata` (title/author/created_at/...) |
| spine 순서 섹션 1개 = 1 `Section` | `sections[N]` |
| `<hp:p>` | `Paragraph` |
| `<hp:run>` | `Run` boundary (charPrIDRef 변경) |
| `<hp:t>` 텍스트 | `Run.text` |
| `<hp:lineBreak/>`, `<hp:columnBreak/>` | `Run.text` 안 `\n` 추가 |
| `<hp:tab/>` | `Run.text` 안 `\t` |
| `<hp:nbSpace/>` | U+00A0 |
| `<hp:fwSpace/>` | U+2007 |
| `<hp:tbl>` | `InlineObject(kind=TABLE)` + `TablePayload` |
| `<hp:tc>` | `Cell` (재귀 paragraphs) |
| `<hp:pic>` `<hp:img binaryItemIDRef>` | `InlineObject(kind=IMAGE)` + `ImagePayload(attachment_ref=ref)` |
| `<hp:fieldBegin>` / `<hp:fieldEnd>` | `InlineObject(kind=FIELD)` |
| `<hp:secPr>` | `Section.page_def` |
| `BinData/<file>` | `Attachment` (id = href) |
| `<hp:p>` `pageBreak` 속성 | `Paragraph.break_after = PAGE` |

### 4.3 HWP3 → IR (best-effort)

`hwplib-py`가 부분 지원 명시. 실제 검증 후 추가 — 일단 다음 정도까지만:

| HWP3 요소 | IR 매핑 |
|---|---|
| 단락 텍스트 | `Paragraph.runs[0].text` (단일 run) |
| 표 | `InlineObject(kind=TABLE)` (셀 텍스트만, 스타일 X) |
| 메타데이터 | best-effort (`Metadata.raw`에 저장) |

`hwplib-py` 검증 결과 안 되면 HWP3는 `Metadata`만 채우고 `sections=()` + `partial=True` 반환.

---

## 5. 텍스트 추출 알고리즘 (포맷 공통)

```python
def document_to_text(doc: Document, include_tables: bool = False, table_placeholder: str = "[표 {n}]") -> str:
    parts: list[str] = []
    table_counter = 0
    for section in doc.sections:
        for para in section.paragraphs:
            line: list[str] = []
            for run in para.runs:
                line.append(run.text)
                if run.inline_marker is not None:
                    obj = para.inline_objects[run.inline_marker]
                    if obj.kind == InlineKind.TABLE:
                        if include_tables and isinstance(obj.payload, TablePayload):
                            line.append(_table_to_markdown(obj.payload))
                        else:
                            table_counter += 1
                            line.append(table_placeholder.format(n=table_counter))
                    elif obj.kind == InlineKind.IMAGE:
                        line.append("[이미지]")
                    elif obj.kind == InlineKind.FIELD and isinstance(obj.payload, FieldPayload):
                        line.append(obj.payload.value or "")
            parts.append("".join(line))
            if para.break_after == BreakKind.PAGE:
                parts.append("\n\f")  # form feed (선택)
    return "\n".join(parts)
```

---

## 6. 표 추출 알고리즘

```python
def document_to_tables(doc: Document) -> list[dict]:
    out = []
    for s_idx, section in enumerate(doc.sections):
        t_idx = 0
        for para in section.paragraphs:
            for obj in para.inline_objects:
                if obj.kind == InlineKind.TABLE and isinstance(obj.payload, TablePayload):
                    cells_text = [
                        [_cell_to_text(c) for c in row]
                        for row in obj.payload.cells
                    ]
                    out.append({
                        "section_index": s_idx,
                        "table_index": t_idx,
                        "rows": obj.payload.rows,
                        "cols": obj.payload.cols,
                        "cells": cells_text,
                        "has_merged_cells": obj.payload.has_merged,
                        "caption": obj.payload.caption,
                    })
                    t_idx += 1
    return out


def _cell_to_text(cell: Cell) -> str:
    return "\n".join(
        "".join(run.text for run in para.runs)
        for para in cell.paragraphs
    )
```

---

## 7. 페이징 / 청킹

### 7.1 char 단위 (기본)
```python
def slice_text(text: str, max_chars: int, offset: int) -> tuple[str, int | None]:
    chunk = text[offset:offset + max_chars]
    next_offset = offset + len(chunk) if (offset + len(chunk)) < len(text) else None
    return chunk, next_offset
```

### 7.2 단락 단위 (옵션)
- `split_at_paragraph_boundary=True` 시 마지막 단락 경계까지만 자름
- 결과의 단락 인덱스 범위를 `[start_para, end_para)` 메타로 함께 반환

### 7.3 페이지 단위 (HWPX만 신뢰 가능)
- HWP5는 페이지 정보 없음 → 비활성화
- HWPX: `Paragraph.break_after == PAGE`로 분리

---

## 8. 부분 파싱 정책

다음 케이스에서 `Document.partial = True`:
1. 일부 섹션 파싱 중 예외 → 해당 섹션 스킵, 나머지 진행
2. 알 수 없는 record tag — skip + warning, 텍스트는 그대로
3. HWPX `<hp:switch>` 분기에서 알려진 case 없음 → default 채택
4. 표 셀 일부 누락 → 빈 Cell로 채움
5. 첨부파일 데이터 로드 실패 → `Attachment.data = None` + warning

`partial=True`인 경우 도구 응답에 `warnings: list[str]` 동봉.

---

## 9. 검증 (parser 단위 테스트 매트릭스)

| 시나리오 | HWP5 | HWPX | HWP3 |
|---|---|---|---|
| 빈 문서 (1 단락 0자) | ✅ | ✅ | △ |
| 한국어 본문 1단락 | ✅ | ✅ | △ |
| 영문/한자/특수문자 혼용 | ✅ | ✅ | — |
| 서로게이트 페어 (이모지) | ✅ | ✅ | — |
| 단락 break (page/column) | ✅ | ✅ | — |
| 표 1×1 | ✅ | ✅ | — |
| 표 N×M (mn 셀 병합) | ✅ | ✅ | — |
| 이미지 1개 | ✅ | ✅ | — |
| 이미지 N개 | ✅ | ✅ | — |
| 비번 잠금 (정상 비번) | ✅ | (미지원) | — |
| 비번 잠금 (오답) | ✅ | (미지원) | — |
| ViewText/DRM | 거부 | 거부 | 거부 |
| 손상 파일 | graceful | graceful | graceful |

---

## 10. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-04-29 | 초안. 분석 결과 통합 후 IR 1차 정의 |
