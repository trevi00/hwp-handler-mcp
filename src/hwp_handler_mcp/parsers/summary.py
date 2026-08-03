"""HWP 5.x ``\\x05HwpSummaryInformation`` 스트림 파싱.

HWP는 표준 OLE property set 을 쓰되 스트림 이름만 다르다 (표준은
``\\x05SummaryInformation``). 그래서 ``olefile.get_metadata()`` 는 이 스트림을
찾지 못하고 전부 ``None`` 을 돌려준다 — 직접 ``getproperties()`` 를 호출해야 한다.

또 하나의 실측 함정: olefile 의 문자열 판독기가 이 스트림에서 NUL 종료를 넘어
뒤쪽 바이트까지 붙여 돌려준다. 예를 들어 작성자 ``mete0r`` 이

    'mete0r\\x00\\x00\\x1f\\x00\\x1d\\x002012년 5월 29일 ...'

로 나온다. 그래서 첫 NUL 에서 잘라야 실제 값이 된다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

SUMMARY_STREAM = "\x05HwpSummaryInformation"

# 표준 SummaryInformation property ID (MS-OLEPS)
PID_TITLE = 2
PID_SUBJECT = 3
PID_AUTHOR = 4
PID_KEYWORDS = 5
PID_COMMENTS = 6
PID_LAST_AUTHOR = 8
PID_REVISION = 9
PID_CREATE_TIME = 12
PID_LAST_SAVE_TIME = 13
PID_PAGE_COUNT = 14

_RAW_LABELS = {
    PID_SUBJECT: "subject",
    PID_KEYWORDS: "keywords",
    PID_COMMENTS: "comments",
    PID_REVISION: "revision",
}


def _clean(value: Any) -> str | None:
    """olefile 이 과다 판독한 문자열을 첫 NUL 에서 자른다."""
    if not isinstance(value, str):
        return None
    text = value.split("\x00", 1)[0].strip()
    return text or None


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    # 미설정 타임스탬프는 FILETIME epoch(1601-01-01)로 온다.
    if value.year <= 1601:
        return None
    return value


def read_hwp5_summary(ole: Any) -> dict[str, Any]:
    """``HwpSummaryInformation`` 을 해석해 정규화된 dict 를 돌려준다.

    스트림이 없거나 파싱에 실패하면 빈 dict 를 돌려준다 (문서 본문 파싱을
    막지 않는다).
    """
    if not ole.exists(SUMMARY_STREAM):
        return {}

    try:
        props = ole.getproperties(SUMMARY_STREAM, convert_time=True)
    except Exception as exc:  # noqa: BLE001 — 라이브러리 경계
        log.debug("HwpSummaryInformation 파싱 실패: %s", exc)
        return {}

    out: dict[str, Any] = {
        "title": _clean(props.get(PID_TITLE)),
        "author": _clean(props.get(PID_AUTHOR)),
        "last_author": _clean(props.get(PID_LAST_AUTHOR)),
        "created_at": _as_datetime(props.get(PID_CREATE_TIME)),
        "modified_at": _as_datetime(props.get(PID_LAST_SAVE_TIME)),
    }

    page_count = props.get(PID_PAGE_COUNT)
    if isinstance(page_count, int) and page_count > 0:
        out["page_count"] = page_count

    raw: dict[str, str] = {}
    for pid, label in _RAW_LABELS.items():
        cleaned = _clean(props.get(pid))
        if cleaned:
            raw[label] = cleaned
    out["raw"] = raw
    return out
