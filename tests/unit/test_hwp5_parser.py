from __future__ import annotations

import struct

from hwp_mcp.ir import BreakKind
from hwp_mcp.parsers.hwp5 import _decode_para_text, _parse_break_type, _read_records


def _make_record(tag_id: int, level: int, body: bytes) -> bytes:
    """평면 레코드 1개 직렬화."""
    size = len(body)
    if size < 0xFFF:
        header = (size << 20) | (level << 10) | (tag_id & 0x3FF)
        return struct.pack("<I", header) + body
    header = (0xFFF << 20) | (level << 10) | (tag_id & 0x3FF)
    return struct.pack("<I", header) + struct.pack("<I", size) + body


def test_read_records_single_short() -> None:
    raw = _make_record(0x42, 0, b"\x01\x02\x03")
    records = list(_read_records(raw))
    assert len(records) == 1
    tag_id, level, body = records[0]
    assert tag_id == 0x42
    assert level == 0
    assert body == b"\x01\x02\x03"


def test_read_records_extended_size() -> None:
    body = b"\xff" * 5000  # > 0xFFF
    raw = _make_record(0x43, 1, body)
    records = list(_read_records(raw))
    assert len(records) == 1
    tag_id, level, recovered = records[0]
    assert tag_id == 0x43
    assert level == 1
    assert recovered == body


def test_read_records_truncated_returns_empty() -> None:
    # 헤더만 있고 body 없음
    raw = struct.pack("<I", (10 << 20) | 0x42)
    records = list(_read_records(raw))
    assert records == []  # log warning + early return


def test_decode_para_text_simple_korean() -> None:
    text = "한글 문서"
    encoded = text.encode("utf-16-le")
    assert _decode_para_text(encoded) == text


def test_decode_para_text_with_line_break() -> None:
    # "ABC" + LF (0x000A) + "DEF"
    encoded = b"A\x00B\x00C\x00\x0a\x00D\x00E\x00F\x00"
    assert _decode_para_text(encoded) == "ABC\nDEF"


def test_decode_para_text_terminates_on_paragraph_end() -> None:
    # "AB" + 0x000D (문단 끝) + "CD" → "AB"만
    encoded = b"A\x00B\x00\x0d\x00C\x00D\x00"
    assert _decode_para_text(encoded) == "AB"


def test_decode_para_text_skips_inline_control_16_bytes() -> None:
    # "A" + inline control (ch=4) 16바이트 + "B"
    encoded = b"A\x00\x04\x00" + b"\x00" * 14 + b"B\x00"
    # ch=0x0004 inline은 16바이트 차지 (헤더 2 + 추가 14)
    assert _decode_para_text(encoded) == "AB"


def test_decode_para_text_special_chars() -> None:
    # 0x18 (묶음 빈칸) + 0x1E (하이픈) + 0x1F (figure space)
    encoded = b"\x18\x00\x1e\x00\x1f\x00"
    result = _decode_para_text(encoded)
    assert result == " - "


def test_decode_para_text_tab_takes_16_bytes() -> None:
    # "A" + TAB(16바이트) + "B"
    encoded = b"A\x00\x09\x00" + b"\x00" * 14 + b"B\x00"
    assert _decode_para_text(encoded) == "A\tB"


def test_parse_break_type_none_when_short() -> None:
    assert _parse_break_type(b"") == BreakKind.NONE
    assert _parse_break_type(b"\x00" * 10) == BreakKind.NONE


def test_parse_break_type_page() -> None:
    body = bytearray(12)
    body[11] = 0x04  # 쪽 나누기
    assert _parse_break_type(bytes(body)) == BreakKind.PAGE


def test_parse_break_type_section() -> None:
    body = bytearray(12)
    body[11] = 0x01  # 구역 나누기
    assert _parse_break_type(bytes(body)) == BreakKind.SECTION


def test_parse_break_type_priority_page_over_section() -> None:
    body = bytearray(12)
    body[11] = 0x05  # 0x04 | 0x01 — 우선순위로 PAGE
    assert _parse_break_type(bytes(body)) == BreakKind.PAGE
