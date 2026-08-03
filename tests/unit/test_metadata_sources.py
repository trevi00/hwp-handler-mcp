"""메타데이터 원천 파서 테스트 (HWP5 SummaryInformation / HWPX content.hpf)."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from hwp_handler_mcp.parsers.opf import read_hwpx_package_metadata
from hwp_handler_mcp.parsers.summary import _as_datetime, _clean

CONTENT_HPF = """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="1.0">
  <opf:metadata>
    <opf:title>2026 사업계획서</opf:title>
    <opf:language>ko</opf:language>
    <opf:meta name="creator" content="text">홍길동</opf:meta>
    <opf:meta name="lastsaveby" content="text">김철수</opf:meta>
    <opf:meta name="CreatedDate" content="text">2026-01-02T03:04:05Z</opf:meta>
    <opf:meta name="ModifiedDate" content="text">2026-02-03T04:05:06Z</opf:meta>
    <opf:meta name="subject" content="text">연간 계획</opf:meta>
  </opf:metadata>
</opf:package>
"""

EMPTY_HPF = """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="1.0">
  <opf:metadata>
    <opf:title/>
    <opf:meta name="creator" content="text"/>
  </opf:metadata>
</opf:package>
"""


def _make_hwpx(target: Path, hpf: str) -> Path:
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/content.hpf", hpf)
    return target


# ------------------------------------------------------------------ HWPX


def test_hwpx_metadata_parsed(tmp_path: Path) -> None:
    path = _make_hwpx(tmp_path / "doc.hwpx", CONTENT_HPF)
    meta = read_hwpx_package_metadata(str(path))

    assert meta["title"] == "2026 사업계획서"
    assert meta["author"] == "홍길동"
    assert meta["last_author"] == "김철수"
    assert meta["created_at"] == datetime.fromisoformat("2026-01-02T03:04:05+00:00")
    assert meta["modified_at"] == datetime.fromisoformat("2026-02-03T04:05:06+00:00")
    assert meta["raw"]["language"] == "ko"
    assert meta["raw"]["subject"] == "연간 계획"


def test_hwpx_empty_tags_normalize_to_none(tmp_path: Path) -> None:
    """<opf:title/> 같은 빈 태그는 빈 문자열이 아니라 None 이어야 한다."""
    path = _make_hwpx(tmp_path / "empty.hwpx", EMPTY_HPF)
    meta = read_hwpx_package_metadata(str(path))
    assert meta.get("title") is None
    assert meta.get("author") is None


def test_hwpx_missing_content_hpf_is_not_fatal(tmp_path: Path) -> None:
    target = tmp_path / "nohpf.hwpx"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
    assert read_hwpx_package_metadata(str(target)) == {}


def test_hwpx_corrupt_container_is_not_fatal(tmp_path: Path) -> None:
    target = tmp_path / "broken.hwpx"
    target.write_bytes(b"not a zip at all")
    assert read_hwpx_package_metadata(str(target)) == {}


# ------------------------------------------------------------------ HWP5


def test_clean_truncates_at_first_nul() -> None:
    """olefile 이 NUL 뒤 바이트까지 붙여 돌려주는 실측 동작을 잘라내야 한다."""
    over_read = "mete0r\x00\x00\x1f\x00\x1d\x002012년 5월 29일 화요일"
    assert _clean(over_read) == "mete0r"


def test_clean_empty_and_non_string() -> None:
    assert _clean("") is None
    assert _clean("   ") is None
    assert _clean(None) is None
    assert _clean(123) is None


def test_as_datetime_rejects_filetime_epoch() -> None:
    """미설정 타임스탬프는 1601-01-01 로 오므로 값으로 취급하면 안 된다."""
    assert _as_datetime(datetime(1601, 1, 1)) is None
    real = datetime(2012, 5, 29, 3, 32, 40)
    assert _as_datetime(real) == real
    assert _as_datetime("2012-05-29") is None
