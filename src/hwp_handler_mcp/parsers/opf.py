"""HWPX 컨테이너의 ``Contents/content.hpf`` (OWPML package) 메타데이터 파싱.

실측한 구조::

    <opf:metadata>
      <opf:title>문서 제목</opf:title>
      <opf:language>ko</opf:language>
      <opf:meta name="creator" content="text">작성자</opf:meta>
      <opf:meta name="lastsaveby" content="text">최종 작성자</opf:meta>
      <opf:meta name="CreatedDate" content="text">2025-09-17T04:32:50Z</opf:meta>
      <opf:meta name="ModifiedDate" content="text">...</opf:meta>
    </opf:metadata>

한컴이 만든 문서와 python-hwpx 가 만든 문서 모두 이 형태를 쓴다. 값이 비어
있는 태그(``<opf:title/>``)가 흔하므로 빈 문자열은 ``None`` 으로 정규화한다.
"""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring as safe_fromstring

log = logging.getLogger(__name__)

CONTENT_HPF = "Contents/content.hpf"

# content.hpf 는 메타데이터 매니페스트라 정상 문서에서 수백 KB를 넘지 않는다.
# 압축 폭탄으로 메모리를 태우지 않도록 상한을 둔다.
MAX_CONTENT_HPF_BYTES = 8 * 1024 * 1024

# <opf:meta name="..."> 의 name → 우리 필드
_META_NAME_MAP = {
    "creator": "author",
    "lastsaveby": "last_author",
    "createddate": "created_at",
    "modifieddate": "modified_at",
}

# raw 로 보존할 부가 정보
_RAW_META_NAMES = {"subject", "description", "keywords", "category"}


def _localname(tag: str) -> str:
    """``{ns}title`` → ``title``."""
    return tag.rsplit("}", 1)[-1].lower()


def _text(elem: ElementTree.Element) -> str | None:
    value = (elem.text or "").strip()
    return value or None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        log.debug("HWPX 날짜 형식 해석 실패: %r", value)
        return None


def read_hwpx_package_metadata(path: str) -> dict[str, Any]:
    """HWPX 파일에서 패키지 메타데이터를 읽는다.

    컨테이너를 열 수 없거나 메타 블록이 없으면 빈 dict 를 돌려준다 (본문 파싱을
    막지 않는다).
    """
    try:
        with zipfile.ZipFile(path) as archive:
            if CONTENT_HPF not in archive.namelist():
                return {}
            info = archive.getinfo(CONTENT_HPF)
            if info.file_size > MAX_CONTENT_HPF_BYTES:
                log.warning(
                    "content.hpf 가 비정상적으로 큽니다 (%d bytes) — 메타데이터를 건너뜁니다",
                    info.file_size,
                )
                return {}
            with archive.open(CONTENT_HPF) as handle:
                payload = handle.read(MAX_CONTENT_HPF_BYTES + 1)
            if len(payload) > MAX_CONTENT_HPF_BYTES:
                # 헤더가 축소 신고한 압축 폭탄 — 실제 읽은 크기로 재판정한다.
                log.warning("content.hpf 압축 해제 크기가 상한을 초과했습니다")
                return {}
    except (OSError, zipfile.BadZipFile) as exc:
        log.debug("HWPX 컨테이너 열기 실패: %s", exc)
        return {}

    try:
        root = safe_fromstring(payload)
    except ElementTree.ParseError as exc:
        log.debug("content.hpf XML 파싱 실패: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001 — defusedxml 이 막은 공격 페이로드
        log.warning("content.hpf 파싱을 거부했습니다 (안전 파서): %s", exc)
        return {}

    out: dict[str, Any] = {}
    raw: dict[str, str] = {}

    for elem in root.iter():
        name = _localname(elem.tag)

        if name == "title":
            out.setdefault("title", _text(elem))
        elif name == "language":
            language = _text(elem)
            if language:
                raw.setdefault("language", language)
        elif name == "meta":
            meta_name = (elem.get("name") or "").strip().lower()
            value = _text(elem)
            if not meta_name or value is None:
                continue
            field = _META_NAME_MAP.get(meta_name)
            if field in ("created_at", "modified_at"):
                out.setdefault(field, _parse_date(value))
            elif field:
                out.setdefault(field, value)
            elif meta_name in _RAW_META_NAMES:
                raw.setdefault(meta_name, value)

    out["raw"] = raw
    return out
