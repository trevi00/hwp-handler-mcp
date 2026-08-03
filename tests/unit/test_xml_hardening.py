"""신뢰할 수 없는 HWPX 를 파싱할 때의 방어 동작 검증.

**반사실 실측 기록** — Python 3.11 의 표준 ``ElementTree`` 는 billion-laughs 를
증폭률 한도로, XXE 를 "undefined entity" 로 이미 거부한다. 그래서 그 두 고전
페이로드로는 defusedxml 의 값어치를 증명할 수 없다 (표준 파서로도 통과하는
공허한 테스트가 된다).

실제로 갈리는 지점은 **증폭률이 낮은 내부 엔티티** 다:

- 표준 ElementTree: ``&secret;`` 을 그대로 확장해 제목에 넣는다.
- defusedxml: ``EntitiesForbidden`` 으로 선언 단계에서 거부한다.

이 차이가 중요한 이유는 추출한 메타데이터가 LLM 컨텍스트로 들어가기 때문이다 —
공격자가 만든 문서의 엔티티에 지시문을 숨기면 프롬프트 인젝션 경로가 된다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwp_handler_mcp.parsers.opf import (
    CONTENT_HPF,
    MAX_CONTENT_HPF_BYTES,
    read_hwpx_package_metadata,
)

# 고전적인 entity 확장 폭탄 (billion laughs). 방어가 없으면 메모리를 태운다.
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:metadata><opf:title>&lol9;</opf:title></opf:metadata>
</opf:package>
"""

# 외부 엔티티(XXE) — 로컬 파일을 읽어가려는 시도.
XXE = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:metadata><opf:title>&xxe;</opf:title></opf:metadata>
</opf:package>
"""


# 증폭률이 낮아 stdlib 한도에 걸리지 않는 내부 엔티티.
# 표준 파서는 이걸 그대로 확장해 제목에 넣는다 — 그래서 진짜 판별자다.
MODEST_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE p [ <!ENTITY secret "INJECTED-BY-ENTITY"> ]>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:metadata><opf:title>&secret;</opf:title></opf:metadata>
</opf:package>
"""


def _hwpx_with(target: Path, hpf: str) -> Path:
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr(CONTENT_HPF, hpf)
    return target


def test_internal_entity_is_not_expanded_into_metadata(tmp_path: Path) -> None:
    """엔티티 내용이 메타데이터로 새어나오면 안 된다 (프롬프트 인젝션 차단).

    이 케이스가 표준 파서와 실제로 갈리는 지점이다. 표준 ElementTree 는
    ``INJECTED-BY-ENTITY`` 를 제목으로 그대로 돌려준다.
    """
    path = _hwpx_with(tmp_path / "entity.hwpx", MODEST_ENTITY)
    result = read_hwpx_package_metadata(str(path))
    assert "INJECTED-BY-ENTITY" not in str(result), (
        "엔티티가 확장되어 메타데이터로 유입됐다 — 안전 파서가 동작하지 않는다"
    )
    assert result.get("title") is None


def test_internal_entity_control_arm_confirms_discrimination() -> None:
    """control arm: 표준 파서라면 확장한다는 것을 같은 페이로드로 확인.

    이게 없으면 위 테스트가 '방어 덕분에 통과'인지 '원래 아무 일도 없어서
    통과'인지 구분되지 않는다.
    """
    from xml.etree import ElementTree as UnsafeET  # noqa: S314 — control arm 목적

    root = UnsafeET.fromstring(MODEST_ENTITY)  # noqa: S314 — 의도적으로 안전하지 않은 파서
    titles = [e.text for e in root.iter() if e.tag.endswith("title")]
    assert titles, "control arm 페이로드에서 title 을 찾지 못했다"
    assert titles[0] == "INJECTED-BY-ENTITY", (
        "표준 파서가 더 이상 확장하지 않는다면 이 방어의 판별자를 다시 골라야 한다"
    )


@pytest.mark.parametrize(
    ("name", "payload"),
    [("billion_laughs", BILLION_LAUGHS), ("xxe", XXE)],
)
def test_classic_attack_payloads_do_not_leak_or_throw(
    name: str, payload: str, tmp_path: Path
) -> None:
    """고전 페이로드는 호출자에게 예외를 던지지 않고 빈 결과로 떨어져야 한다.

    주의: Python 3.11 표준 파서도 이 둘은 거부하므로, 이 테스트는 defusedxml
    의 값어치가 아니라 **우리 함수의 계약**(예외 누출 없음, 데이터 유출 없음)을
    고정한다.
    """
    path = _hwpx_with(tmp_path / f"{name}.hwpx", payload)
    result = read_hwpx_package_metadata(str(path))
    assert result.get("title") is None
    assert "root:" not in str(result)


def test_oversized_content_hpf_is_skipped(tmp_path: Path) -> None:
    """압축 폭탄 방어: 상한을 넘는 content.hpf 는 파싱하지 않는다."""
    target = tmp_path / "bomb.hwpx"
    filler = b"<opf:package>" + b"A" * (MAX_CONTENT_HPF_BYTES + 1024) + b"</opf:package>"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr(CONTENT_HPF, filler)
    assert read_hwpx_package_metadata(str(target)) == {}


def test_normal_document_still_parses(tmp_path: Path) -> None:
    """방어가 정상 문서까지 막아버리면 안 된다 (control arm)."""
    good = """<?xml version="1.0"?>
    <opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
      <opf:metadata><opf:title>정상 문서</opf:title></opf:metadata>
    </opf:package>
    """
    path = _hwpx_with(tmp_path / "good.hwpx", good)
    assert read_hwpx_package_metadata(str(path))["title"] == "정상 문서"
