"""MCP SDK 1.x / 2.x 양쪽을 흡수하는 호환 레이어.

SDK 2.0에서 세 가지가 깨졌다:

- ``mcp.server.fastmcp.FastMCP`` → ``mcp.server.mcpserver.MCPServer``
- ``mcp.shared.exceptions.McpError`` → ``...MCPError``
- 예외 생성자: 1.x는 ``McpError(ErrorData)``, 2.x는 ``MCPError(code, message, data)``

데코레이터 인터페이스(``.tool()``)와 실행 인터페이스(``.run(transport=...)``)는
두 메이저에서 동일하므로, 위 세 지점만 해석해주면 나머지 코드는 분기 없이 돌아간다.
"""

from __future__ import annotations

from typing import Any, cast

from mcp.types import ErrorData

__all__ = [
    "MCP_SDK_MAJOR",
    "McpError",
    "ServerClass",
    "build_mcp_error",
    "package_version",
]

DISTRIBUTION_NAME = "hwp-handler-mcp"


def package_version() -> str:
    """설치된 배포판 버전. 클라이언트의 ``serverInfo.version`` 에 실린다.

    소스 트리에서 바로 실행하는 등 배포판 메타데이터가 없을 수 있으므로,
    없을 때는 서버 기동을 막지 않고 빈 문자열을 돌려준다.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:  # pragma: no cover — 설치 없이 실행한 경우
        return ""


def _resolve_server() -> tuple[Any, int]:
    try:  # MCP SDK >= 2.0
        from mcp.server.mcpserver import MCPServer

        return MCPServer, 2
    except ImportError:  # MCP SDK 1.x
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

        return FastMCP, 1


def _resolve_error() -> Any:
    import mcp.shared.exceptions as _ex

    # 2.x는 MCPError, 1.x는 McpError. 둘 중 존재하는 쪽을 쓴다.
    err = getattr(_ex, "MCPError", None) or getattr(_ex, "McpError", None)
    if err is None:  # pragma: no cover — SDK가 또 이름을 바꾼 경우
        raise ImportError(
            "MCP SDK에서 MCPError/McpError를 찾을 수 없습니다. "
            "지원 범위 밖의 SDK 버전일 수 있습니다."
        )
    return err


ServerClass, MCP_SDK_MAJOR = _resolve_server()
McpError = _resolve_error()


def build_mcp_error(error_data: ErrorData) -> Exception:
    """``ErrorData`` 하나로 두 메이저 모두에서 예외 인스턴스를 만든다.

    2.x는 ``from_error_data`` 클래스메서드를 제공하고, 1.x는 생성자가
    ``ErrorData`` 를 그대로 받는다.
    """
    from_error_data = getattr(McpError, "from_error_data", None)
    if from_error_data is not None:  # MCP SDK >= 2.0
        return cast(Exception, from_error_data(error_data))
    return cast(Exception, McpError(error_data))  # MCP SDK 1.x
