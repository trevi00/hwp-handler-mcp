from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from hwp_mcp.logging_setup import setup_logging
from hwp_mcp.tools.attach import (
    AttachmentContent,
    ListAttachmentsResult,
    list_attachments_impl,
    read_attachment_impl,
)
from hwp_mcp.tools.inspect import (
    FormatInfo,
    StructureReport,
    detect_format_impl,
    inspect_structure_impl,
)
from hwp_mcp.tools.metadata import MetadataResult, extract_metadata_impl
from hwp_mcp.tools.tables import ExtractTablesResult, extract_tables_impl
from hwp_mcp.tools.text import ExtractText, extract_text_impl

setup_logging()

mcp = FastMCP("hwp-mcp")


@mcp.tool()
def detect_format(path: str) -> FormatInfo:
    """HWP/HWPX 파일의 포맷, 버전, 보안 플래그(암호/DRM/배포)를 감지합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
    """
    return detect_format_impl(path)


@mcp.tool()
def extract_text(
    path: str,
    password: str | None = None,
    max_chars: int = 100_000,
    offset: int = 0,
    include_tables: bool = False,
    include_images: bool = False,
) -> ExtractText:
    """HWP/HWPX 본문 텍스트를 추출합니다. 비밀번호 보호 문서는 password 인자로 풀 수 있습니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        password: 비밀번호 보호 문서의 비밀번호 (Phase B 예정).
        max_chars: 반환할 텍스트의 최대 문자 수 (기본 100000).
        offset: 페이징 오프셋 (기본 0).
        include_tables: True면 표를 Markdown으로 인라인. False면 [표 N] placeholder.
        include_images: True면 이미지 위치에 [이미지] 마커.
    """
    return extract_text_impl(
        path,
        password=password,
        max_chars=max_chars,
        offset=offset,
        include_tables=include_tables,
        include_images=include_images,
    )


@mcp.tool()
def extract_metadata(path: str, password: str | None = None) -> MetadataResult:
    """문서의 제목, 작성자, 생성일 등 메타데이터를 추출합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        password: 비밀번호 보호 문서의 비밀번호 (Phase B 예정).
    """
    return extract_metadata_impl(path, password=password)


@mcp.tool()
def inspect_structure(path: str, include_data_preview: bool = False) -> StructureReport:
    """파일을 변형하지 않고 컨테이너 구조(스트림/엔트리/레코드)를 dump합니다. 포렌식 분석용.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        include_data_preview: True면 각 스트림 첫 64바이트 hex 미리보기 포함.
    """
    return inspect_structure_impl(path, include_data_preview=include_data_preview)


@mcp.tool()
def extract_tables(
    path: str,
    password: str | None = None,
    section_index: int | None = None,
) -> ExtractTablesResult:
    """문서 안의 모든 표를 행/열 구조로 추출합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        password: 비밀번호 보호 문서의 비밀번호 (Phase B 예정).
        section_index: 특정 섹션만 추출 (None이면 전체).
    """
    return extract_tables_impl(path, password=password, section_index=section_index)


@mcp.tool()
def list_attachments(path: str, password: str | None = None) -> ListAttachmentsResult:
    """임베딩된 이미지/OLE 객체/차트 목록을 반환합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        password: 비밀번호 보호 문서의 비밀번호 (Phase B 예정).
    """
    return list_attachments_impl(path, password=password)


@mcp.tool()
def read_attachment(
    path: str,
    storage_id: str,
    password: str | None = None,
    max_size_bytes: int = 5_242_880,
) -> AttachmentContent:
    """특정 첨부 파일의 내용을 base64로 반환합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        storage_id: list_attachments에서 받은 storage_id.
        password: 비밀번호 보호 문서의 비밀번호 (Phase B 예정).
        max_size_bytes: 최대 반환 크기 (기본 5MB).
    """
    return read_attachment_impl(
        path,
        storage_id=storage_id,
        password=password,
        max_size_bytes=max_size_bytes,
    )
