"""HWPX end-to-end 통합 테스트 (synthetic fixture 사용)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwp_handler_mcp.tools.attach import list_attachments_impl, read_attachment_impl
from hwp_handler_mcp.tools.inspect import detect_format_impl, inspect_structure_impl
from hwp_handler_mcp.tools.metadata import extract_metadata_impl
from hwp_handler_mcp.tools.tables import extract_tables_impl
from hwp_handler_mcp.tools.text import extract_text_impl

pytestmark = pytest.mark.integration


def test_detect_format_hwpx(synthetic_hwpx: Path) -> None:
    info = detect_format_impl(str(synthetic_hwpx))
    assert info.format == "hwpx"
    assert info.encrypted is False
    assert info.drm is False
    assert info.distribution is False


def test_extract_text_hwpx_returns_korean(synthetic_hwpx: Path) -> None:
    result = extract_text_impl(str(synthetic_hwpx))
    assert "안녕하세요" in result.text
    assert "두 번째 문단" in result.text
    assert "줄바꿈 후 텍스트" in result.text
    assert result.format == "hwpx"
    assert result.section_count >= 1
    assert result.partial is False


def test_extract_text_hwpx_pagination(synthetic_hwpx: Path) -> None:
    full = extract_text_impl(str(synthetic_hwpx))
    chunk1 = extract_text_impl(str(synthetic_hwpx), max_chars=5)
    assert chunk1.truncated is True
    assert chunk1.next_offset == 5
    assert chunk1.text == full.text[:5]
    chunk2 = extract_text_impl(str(synthetic_hwpx), max_chars=5, offset=5)
    assert chunk2.text == full.text[5:10]


def test_extract_metadata_hwpx(synthetic_hwpx: Path) -> None:
    md = extract_metadata_impl(str(synthetic_hwpx))
    assert md.format == "hwpx"
    assert md.section_count >= 1


def test_inspect_structure_hwpx(synthetic_hwpx: Path) -> None:
    report = inspect_structure_impl(str(synthetic_hwpx))
    assert report.format == "hwpx"
    names = {s.name for s in report.streams}
    assert "Contents/content.hpf" in names
    assert "Contents/section0.xml" in names
    assert "BinData/image1.png" in names


def test_list_attachments_hwpx(synthetic_hwpx: Path) -> None:
    result = list_attachments_impl(str(synthetic_hwpx))
    assert result.total_count == 1
    image = result.attachments[0]
    assert image.is_image
    assert image.media_type == "image/png"
    assert image.filename == "image1.png"


def test_read_attachment_hwpx_roundtrip(synthetic_hwpx: Path, png_payload: bytes) -> None:
    import base64

    result = read_attachment_impl(str(synthetic_hwpx), storage_id="BinData/image1.png")
    assert base64.b64decode(result.content_base64) == png_payload


def test_extract_tables_hwpx_no_tables(synthetic_hwpx: Path) -> None:
    """현재 fixture에는 표 없음 — total_count 0 기대."""
    result = extract_tables_impl(str(synthetic_hwpx))
    assert result.total_count == 0
