from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwp_handler_mcp._compat import McpError
from hwp_handler_mcp.tools.tables import extract_tables_impl


def test_extract_tables_hwp5_returns_warning(tmp_path: Path) -> None:
    """HWP5 표 분해는 미지원 — 조용한 0개가 아니라 warning을 동봉해야 한다."""
    target = tmp_path / "fake.hwp"
    target.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 1024)
    result = extract_tables_impl(str(target))
    assert result.total_count == 0
    assert result.warnings, "HWP5에서 표 0개를 반환하면서 warning이 없으면 안 된다"
    assert any("HWP5" in w and "지원하지 않습니다" in w for w in result.warnings)


def test_extract_tables_password_rejected(tmp_path: Path) -> None:
    target = tmp_path / "fake.hwpx"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("Contents/content.hpf", "<package/>")
    with pytest.raises(McpError) as exc_info:
        extract_tables_impl(str(target), password="x")  # noqa: S106
    assert exc_info.value.error.data["code"] == "PASSWORD_REQUIRED"
