from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from mcp.shared.exceptions import McpError

from hwp_mcp.tools.tables import extract_tables_impl


def test_extract_tables_hwp5_returns_warning(tmp_path: Path) -> None:
    """HWP5는 Phase A에서 표 추출 미지원 → warning 동봉."""
    # 최소한의 HWP5 시그니처만 갖춘 OLE 컨테이너는 만들기 어려우므로,
    # 이 테스트는 파일 매직만 검증하고 INVALID_FORMAT을 기대.
    # 실제 HWP5 표 추출 검증은 Phase B integration test.
    target = tmp_path / "fake.hwp"
    target.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 1024)
    # detect_magic은 HWP5로 판정 → Phase A에서는 빈 결과 + warning
    result = extract_tables_impl(str(target))
    assert result.total_count == 0
    assert any("Phase B" in w for w in result.warnings)


def test_extract_tables_password_rejected(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
    with pytest.raises(McpError) as exc_info:
        extract_tables_impl(str(target), password="x")  # noqa: S106
    assert exc_info.value.error.data["code"] == "PASSWORD_REQUIRED"
