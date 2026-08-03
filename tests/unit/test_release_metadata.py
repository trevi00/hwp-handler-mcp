"""릴리스 메타데이터 정합성.

버전 문자열이 ``pyproject.toml`` 과 ``server.json`` 세 군데에 중복되어 있다.
어긋난 채로 태그를 달면 PyPI 는 올라가고 MCP 레지스트리는 없는 버전을 가리키는,
사후에야 드러나는 실패가 된다. 사람이 기억하는 대신 테스트가 잡는다.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def server_json() -> dict:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_server_json_version_matches_pyproject(pyproject: dict, server_json: dict) -> None:
    expected = pyproject["project"]["version"]
    assert server_json["version"] == expected, (
        f"server.json version={server_json['version']} != pyproject {expected}"
    )
    for package in server_json["packages"]:
        assert package["version"] == expected, (
            f"packages[].version={package['version']} != pyproject {expected}"
        )


def test_server_json_package_name_matches_distribution(pyproject: dict, server_json: dict) -> None:
    expected = pyproject["project"]["name"]
    for package in server_json["packages"]:
        assert package["identifier"] == expected


def test_readme_carries_mcp_name_token(server_json: dict) -> None:
    """레지스트리는 PyPI 설명(README)의 이 토큰으로 소유권을 확인한다.

    사라지면 배포 파이프라인 마지막 단계에서만 실패하므로 여기서 고정한다.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    token = f"mcp-name: {server_json['name']}"
    assert token in readme, f"README 에 {token!r} 이 없다"


def test_description_within_registry_limit(server_json: dict) -> None:
    """MCP 레지스트리 스키마의 description maxLength 는 100 이다."""
    assert len(server_json["description"]) <= 100
