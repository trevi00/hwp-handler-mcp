"""실제 한컴 오피스가 생성한 .hwp 파일에 대한 회귀 테스트.

합성 픽스처는 파서 작성자가 픽스처도 작성하므로 내부 정합성만 확인된다.
실제 문서에서만 드러나는 결함을 잡기 위해 실물 코퍼스를 돌린다
(출처/라이선스는 ``tests/fixtures/real_hwp5/ATTRIBUTION.md``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwp_handler_mcp.ir import Format
from hwp_handler_mcp.tools.inspect import detect_format_impl, inspect_structure_impl
from hwp_handler_mcp.tools.tables import extract_tables_impl
from hwp_handler_mcp.tools.text import extract_text_impl

pytestmark = pytest.mark.integration

CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "real_hwp5"

# (파일명, 본문에 반드시 포함되어야 하는 문자열 | None=빈 문서)
CORPUS: list[tuple[str, str | None]] = [
    ("blank.hwp", None),
    ("footnote_endnote.hwp", "sssd"),
    ("header_footer.hwp", "개요1"),
    ("textbox.hwp", "ABC"),
]


def _path(name: str) -> Path:
    p = CORPUS_DIR / name
    if not p.exists():  # pragma: no cover — 픽스처 누락 방지용
        pytest.fail(f"실물 픽스처 누락: {p}")
    return p


@pytest.mark.parametrize(("name", "expected_substring"), CORPUS)
def test_real_hwp5_text_extraction(name: str, expected_substring: str | None) -> None:
    """실제 .hwp 본문 텍스트가 뽑히는가."""
    result = extract_text_impl(str(_path(name)))
    assert result.format == Format.HWP5
    if expected_substring is None:
        assert result.total_char_count == 0, "빈 문서인데 텍스트가 나왔다"
    else:
        assert expected_substring in result.text, (
            f"{name}: 기대 문자열 {expected_substring!r} 없음. 실제={result.text[:80]!r}"
        )


@pytest.mark.parametrize(("name", "_expected"), CORPUS)
def test_real_hwp5_version_detected(name: str, _expected: str | None) -> None:
    """버전 문자열이 5.x 형태로 파싱되는가 (v5.0.3.4 등)."""
    info = detect_format_impl(str(_path(name)))
    assert info.format == Format.HWP5
    assert info.version.startswith("5."), f"{name}: 버전 파싱 실패 — {info.version!r}"
    assert not info.encrypted
    assert not info.drm


@pytest.mark.parametrize(("name", "_expected"), CORPUS)
def test_real_hwp5_structure_dump(name: str, _expected: str | None) -> None:
    """구조 dump가 FileHeader를 포함한 실제 스트림을 보고하는가."""
    report = inspect_structure_impl(str(_path(name)))
    stream_names = {s.name for s in report.streams}
    assert "FileHeader" in stream_names, f"{name}: FileHeader 스트림 없음"
    assert len(stream_names) > 1


def test_real_hwp5_tables_warn_instead_of_silent_zero() -> None:
    """HWP5 표 미지원은 '조용한 0개'가 아니라 warning으로 드러나야 한다."""
    result = extract_tables_impl(str(_path("textbox.hwp")))
    assert result.total_count == 0
    assert result.warnings, "0개를 반환하면서 warning이 없으면 사용자가 알 수 없다"
