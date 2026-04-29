"""MCP 서버 도구 등록 검증 + stdout 청결성."""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


def test_all_seven_tools_registered() -> None:
    from hwp_mcp.server import mcp

    async def _list():
        return await mcp.list_tools()

    tools = asyncio.run(_list())
    names = {t.name for t in tools}
    expected = {
        "detect_format",
        "extract_text",
        "extract_metadata",
        "inspect_structure",
        "extract_tables",
        "list_attachments",
        "read_attachment",
    }
    assert names == expected, f"missing: {expected - names}, extra: {names - expected}"


def test_tool_descriptions_are_korean() -> None:
    from hwp_mcp.server import mcp

    async def _list():
        return await mcp.list_tools()

    tools = asyncio.run(_list())
    for tool in tools:
        assert tool.description is not None
        # 한국어 문자(가나다 영역)가 description에 들어 있어야 함
        assert any("가" <= c <= "힣" for c in tool.description), (
            f"{tool.name}: 한국어 description 없음"
        )


def test_no_stdout_pollution_on_import(capfd: pytest.CaptureFixture[str]) -> None:
    """stdio MCP 서버는 stdout이 JSON-RPC 전용 — import 시 출력 0이어야 함."""
    # capture before import
    out_before, _ = capfd.readouterr()
    # 모듈을 새로 import
    import importlib

    import hwp_mcp.server

    importlib.reload(hwp_mcp.server)
    out_after, err_after = capfd.readouterr()
    assert out_after == "", f"stdout polluted on import: {out_after!r}"


def test_logger_writes_to_stderr_not_stdout(capfd: pytest.CaptureFixture[str]) -> None:
    """로깅이 stderr로만 가는지 확인 (MCP stdio 통신 안전성)."""
    import logging

    from hwp_mcp.logging_setup import setup_logging

    setup_logging()
    log = logging.getLogger("hwp_mcp.test_check")
    log.warning("테스트 로그 한글")
    out, err = capfd.readouterr()
    assert out == "", f"stdout에 로그 누출: {out!r}"
    # err에 메시지가 있을 수도 있고 없을 수도 있음 (root logger 설정에 따라)
    # 핵심은 stdout이 깨끗한 것
