"""통합 테스트용 합성 HWPX fixture 생성기.

올바른 OWPML 구조를 흉내내어 python-hwpx가 파싱할 수 있는 최소 ZIP을 만든다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9c"
    b"c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x88c\xfa\x00\x00\x00\x00"
    b"IEND\xaeB`\x82"
)

_NS_OPF = 'xmlns:opf="http://www.idpf.org/2007/opf/"'
_NS_HP = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
_NS_HS = 'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="Contents/content.hpf" media-type="application/hwp+zip"/>
  </rootfiles>
</container>
"""

VERSION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" \
targetApplication="WORDPROCESSOR" major="5" minor="0" micro="3" buildNumber="0"/>
"""

CONTENT_HPF = f"""<?xml version="1.0" encoding="UTF-8"?>
<opf:package version="1.0" {_NS_OPF}>
  <opf:metadata>
    <dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">테스트 문서</dc:title>
    <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">홍길동</dc:creator>
  </opf:metadata>
  <opf:manifest>
    <opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>
    <opf:item id="image1" href="BinData/image1.png" media-type="image/png"/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="section0" linear="yes"/>
  </opf:spine>
</opf:package>
"""

HEADER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>
</hh:head>
"""

SECTION0_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<hs:sec {_NS_HS} {_NS_HP}>
  <hp:p>
    <hp:run>
      <hp:t>안녕하세요, 첫 문단입니다.</hp:t>
    </hp:run>
  </hp:p>
  <hp:p>
    <hp:run>
      <hp:t>두 번째 문단</hp:t>
      <hp:lineBreak/>
      <hp:t>줄바꿈 후 텍스트</hp:t>
    </hp:run>
  </hp:p>
</hs:sec>
"""


def _build_hwpx(target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("version.xml", VERSION_XML)
        z.writestr("META-INF/container.xml", CONTAINER_XML)
        z.writestr("Contents/content.hpf", CONTENT_HPF)
        z.writestr("Contents/header.xml", HEADER_XML)
        z.writestr("Contents/section0.xml", SECTION0_XML)
        z.writestr("BinData/image1.png", PNG_1x1)


@pytest.fixture
def synthetic_hwpx(tmp_path: Path) -> Path:
    """합성 HWPX 파일 (1 섹션, 2 단락, 1 이미지)."""
    target = tmp_path / "synthetic.hwpx"
    _build_hwpx(target)
    return target


@pytest.fixture
def png_payload() -> bytes:
    return PNG_1x1
