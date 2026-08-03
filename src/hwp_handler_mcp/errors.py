from __future__ import annotations

from enum import StrEnum
from typing import Any, NoReturn

from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData

from hwp_handler_mcp._compat import build_mcp_error


class ErrorCode(StrEnum):
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_FORMAT = "INVALID_FORMAT"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"  # noqa: S105 — error code name, not a password
    WRONG_PASSWORD = "WRONG_PASSWORD"  # noqa: S105
    DISTRIBUTION_PROTECTED = "DISTRIBUTION_PROTECTED"
    DRM_PROTECTED = "DRM_PROTECTED"
    PKI_ENCRYPTED = "PKI_ENCRYPTED"
    ZIP_BOMB_SUSPECTED = "ZIP_BOMB_SUSPECTED"
    OFFSET_OUT_OF_RANGE = "OFFSET_OUT_OF_RANGE"
    ATTACHMENT_NOT_FOUND = "ATTACHMENT_NOT_FOUND"
    ATTACHMENT_TOO_LARGE = "ATTACHMENT_TOO_LARGE"
    PARTIAL_PARSE_FAILED = "PARTIAL_PARSE_FAILED"
    INTERNAL = "INTERNAL_ERROR"


_KOREAN_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.FILE_NOT_FOUND: "파일을 찾을 수 없습니다",
    ErrorCode.FILE_TOO_LARGE: "파일이 너무 큼 (한도 200MB)",
    ErrorCode.PERMISSION_DENIED: "파일 읽기 권한이 없습니다",
    ErrorCode.INVALID_FORMAT: "HWP/HWPX 파일이 아니거나 손상됨",
    ErrorCode.UNSUPPORTED_VERSION: "지원하지 않는 HWP 버전",
    ErrorCode.PASSWORD_REQUIRED: "비밀번호로 보호된 문서. password 인자 필요",
    ErrorCode.WRONG_PASSWORD: "비밀번호가 일치하지 않거나 지원하지 않는 암호 알고리즘",
    ErrorCode.DISTRIBUTION_PROTECTED: "한컴 배포용(ViewText) 보호 문서는 정책상 미지원",
    ErrorCode.DRM_PROTECTED: "DRM 보호 문서는 정책상 미지원",
    ErrorCode.PKI_ENCRYPTED: "공개키 암호화 문서는 미지원",
    ErrorCode.ZIP_BOMB_SUSPECTED: "압축 해제 결과가 한도 초과",
    ErrorCode.OFFSET_OUT_OF_RANGE: "offset이 전체 텍스트 범위 초과",
    ErrorCode.ATTACHMENT_NOT_FOUND: "첨부 파일을 찾을 수 없습니다",
    ErrorCode.ATTACHMENT_TOO_LARGE: "첨부 파일이 너무 큼",
    ErrorCode.PARTIAL_PARSE_FAILED: "파일을 부분 파싱할 수 없습니다",
    ErrorCode.INTERNAL: "내부 오류 — 자세한 내용은 로그 참조",
}

_USER_INPUT_ERRORS: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.FILE_NOT_FOUND,
        ErrorCode.PERMISSION_DENIED,
        ErrorCode.INVALID_FORMAT,
        ErrorCode.PASSWORD_REQUIRED,
        ErrorCode.WRONG_PASSWORD,
        ErrorCode.OFFSET_OUT_OF_RANGE,
        ErrorCode.ATTACHMENT_NOT_FOUND,
    }
)


def raise_hwp_error(
    code: ErrorCode,
    *,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> NoReturn:
    """공통 에러 헬퍼. password 같은 비밀 정보는 절대 extra에 담지 않을 것."""
    base_message = _KOREAN_MESSAGES[code]
    message = f"{base_message}: {detail}" if detail else base_message
    rpc_code = INVALID_PARAMS if code in _USER_INPUT_ERRORS else INTERNAL_ERROR
    data: dict[str, Any] = {"code": code.value}
    if extra:
        for key, value in extra.items():
            if key.lower() in ("password", "passwd", "pw"):
                continue
            data[key] = value
    raise build_mcp_error(ErrorData(code=rpc_code, message=message, data=data))
