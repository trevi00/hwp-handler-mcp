"""MCP 서버 도구 등록 검증 + stdout 청결성."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


READ_TOOLS = {
    "detect_format",
    "extract_text",
    "extract_metadata",
    "inspect_structure",
    "extract_tables",
    "list_attachments",
    "read_attachment",
    "convert_to_markdown",
}

WRITE_TOOLS = {
    "create_document",
    "replace_text",
    "fill_form",
    "set_header_footer",
}


def _tools():
    """MCP SDK 1.x는 list_tools()가 코루틴, 2.x는 동기 — 둘 다 받는다."""
    from hwp_handler_mcp.server import mcp

    result = mcp.list_tools()
    if hasattr(result, "__await__"):
        return asyncio.run(result)  # type: ignore[arg-type]
    return result


def test_all_tools_registered() -> None:
    names = {t.name for t in _tools()}
    expected = READ_TOOLS | WRITE_TOOLS
    assert names == expected, f"missing: {expected - names}, extra: {names - expected}"


def test_tool_descriptions_are_korean() -> None:
    for tool in _tools():
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

    import hwp_handler_mcp.server

    importlib.reload(hwp_handler_mcp.server)
    out_after, err_after = capfd.readouterr()
    assert out_after == "", f"stdout polluted on import: {out_after!r}"


def test_logger_writes_to_stderr_not_stdout(capfd: pytest.CaptureFixture[str]) -> None:
    """로깅이 stderr로만 가는지 확인 (MCP stdio 통신 안전성)."""
    import logging

    from hwp_handler_mcp.logging_setup import setup_logging

    setup_logging()
    log = logging.getLogger("hwp_handler_mcp.test_check")
    log.warning("테스트 로그 한글")
    out, err = capfd.readouterr()
    assert out == "", f"stdout에 로그 누출: {out!r}"
    # err에 메시지가 있을 수도 있고 없을 수도 있음 (root logger 설정에 따라)
    # 핵심은 stdout이 깨끗한 것
