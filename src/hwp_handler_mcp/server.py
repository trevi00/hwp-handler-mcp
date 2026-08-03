from __future__ import annotations

from hwp_handler_mcp._compat import ServerClass, package_version
from hwp_handler_mcp.logging_setup import setup_logging
from hwp_handler_mcp.tools.attach import (
    AttachmentContent,
    ListAttachmentsResult,
    list_attachments_impl,
    read_attachment_impl,
)
from hwp_handler_mcp.tools.edit import (
    FillResult,
    MarkdownResult,
    ReplaceResult,
    WriteResult,
    convert_to_markdown_impl,
    create_document_impl,
    fill_form_impl,
    replace_text_impl,
    set_header_footer_impl,
)
from hwp_handler_mcp.tools.inspect import (
    FormatInfo,
    StructureReport,
    detect_format_impl,
    inspect_structure_impl,
)
from hwp_handler_mcp.tools.metadata import MetadataResult, extract_metadata_impl
from hwp_handler_mcp.tools.tables import ExtractTablesResult, extract_tables_impl
from hwp_handler_mcp.tools.text import ExtractText, extract_text_impl

setup_logging()

mcp = ServerClass("hwp-handler-mcp", version=package_version())


# ---------------------------------------------------------------------------
# 읽기 — HWP 5.x(.hwp) + HWPX(.hwpx)
# ---------------------------------------------------------------------------


@mcp.tool()
def detect_format(path: str) -> FormatInfo:
    """HWP/HWPX 파일의 포맷, 버전, 보안 플래그(암호/DRM/배포본)를 감지합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
    """
    return detect_format_impl(path)


@mcp.tool()
def extract_text(
    path: str,
    max_chars: int = 100_000,
    offset: int = 0,
    include_tables: bool = False,
    include_images: bool = False,
) -> ExtractText:
    """HWP/HWPX 본문 텍스트를 추출합니다. .hwp와 .hwpx 모두 지원합니다.

    암호화된 문서는 지원하지 않으며 명시적 오류를 반환합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        max_chars: 반환할 텍스트의 최대 문자 수 (기본 100000).
        offset: 페이징 오프셋 (기본 0).
        include_tables: True면 표를 Markdown으로 인라인. False면 [표 N] placeholder.
        include_images: True면 이미지 위치에 [이미지] 마커.
    """
    return extract_text_impl(
        path,
        max_chars=max_chars,
        offset=offset,
        include_tables=include_tables,
        include_images=include_images,
    )


@mcp.tool()
def extract_metadata(path: str) -> MetadataResult:
    """문서의 제목, 작성자, 생성일 등 메타데이터를 추출합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
    """
    return extract_metadata_impl(path)


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
    section_index: int | None = None,
) -> ExtractTablesResult:
    """문서 안의 모든 표를 행/열 구조로 추출합니다.

    HWPX(.hwpx)에서 동작합니다. HWP5(.hwp) 바이너리는 표 구조 분해를 아직
    지원하지 않으며, 그 경우 warnings로 알려줍니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        section_index: 특정 섹션만 추출 (None이면 전체).
    """
    return extract_tables_impl(path, section_index=section_index)


@mcp.tool()
def list_attachments(path: str) -> ListAttachmentsResult:
    """임베딩된 이미지/OLE 객체/차트 목록을 반환합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
    """
    return list_attachments_impl(path)


@mcp.tool()
def read_attachment(
    path: str,
    storage_id: str,
    max_size_bytes: int = 5_242_880,
) -> AttachmentContent:
    """특정 첨부 파일의 내용을 base64로 반환합니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
        storage_id: list_attachments에서 받은 storage_id.
        max_size_bytes: 최대 반환 크기 (기본 5MB).
    """
    return read_attachment_impl(
        path,
        storage_id=storage_id,
        max_size_bytes=max_size_bytes,
    )


@mcp.tool()
def convert_to_markdown(path: str) -> MarkdownResult:
    """문서를 Markdown으로 변환합니다. 문서 내용을 LLM에 그대로 먹일 때 씁니다.

    HWPX는 표까지 Markdown 표로 변환됩니다. HWP5(.hwp)는 본문 텍스트만
    변환되며 그 한계를 warnings로 알려줍니다.

    Args:
        path: HWP 또는 HWPX 파일의 절대경로.
    """
    return convert_to_markdown_impl(path)


# ---------------------------------------------------------------------------
# 쓰기 — HWPX(.hwpx) 전용
#
# HWP5(.hwp) 바이너리 저작은 순수 Python 구현이 존재하지 않아 지원하지 않는다.
# 쓰기 도구에 .hwp를 넘기면 명시적 오류를 반환한다.
# ---------------------------------------------------------------------------


@mcp.tool()
def create_document(
    output_path: str,
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
    header_text: str | None = None,
    footer_text: str | None = None,
    overwrite: bool = False,
) -> WriteResult:
    """새 HWPX 문서를 생성합니다.

    Args:
        output_path: 만들 .hwpx 파일의 절대경로.
        paragraphs: 본문 문단 목록 (순서대로 기록).
        tables: 표 목록. 각 표는 행×열 2차원 문자열 배열.
        header_text: 머리말 (생략 가능).
        footer_text: 꼬리말 (생략 가능).
        overwrite: True여야 기존 파일을 덮어씁니다. 기본 False로 사고를 막습니다.
    """
    return create_document_impl(
        output_path,
        paragraphs=paragraphs,
        tables=tables,
        header_text=header_text,
        footer_text=footer_text,
        overwrite=overwrite,
    )


@mcp.tool()
def replace_text(
    path: str,
    replacements: dict[str, str],
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> ReplaceResult:
    """HWPX 본문 텍스트를 일괄 치환합니다. 패턴별 치환 횟수를 돌려줍니다.

    Args:
        path: 원본 .hwpx 절대경로.
        replacements: {찾을문자열: 바꿀문자열} 매핑.
        output_path: 결과를 쓸 경로. 생략하면 in_place=True가 필요합니다.
        overwrite: 출력 파일이 이미 있을 때 덮어쓰려면 True.
        in_place: output_path 없이 원본을 직접 수정하려면 True.
    """
    return replace_text_impl(
        path,
        replacements=replacements,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )


@mcp.tool()
def fill_form(
    path: str,
    mappings: dict[str, str],
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> FillResult:
    """표 라벨을 기준으로 인접 셀에 값을 채웁니다. 한글 양식/신청서 작성용입니다.

    키는 "라벨 > 방향" 경로입니다. 방향은 right / left / below / above.
    예: {"성명 > right": "김철수", "부서 > right": "개발팀"}

    적용된 항목과 실패한 항목을 각각 돌려주므로, 라벨이 문서에 없으면
    조용히 넘어가지 않고 failed로 보고됩니다.

    Args:
        path: 원본 .hwpx 절대경로 (양식 문서).
        mappings: {"라벨 > 방향": "채울값"} 매핑.
        output_path: 결과를 쓸 경로. 생략하면 in_place=True가 필요합니다.
        overwrite: 출력 파일이 이미 있을 때 덮어쓰려면 True.
        in_place: output_path 없이 원본을 직접 수정하려면 True.
    """
    return fill_form_impl(
        path,
        mappings=mappings,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )


@mcp.tool()
def set_header_footer(
    path: str,
    header_text: str | None = None,
    footer_text: str | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    in_place: bool = False,
) -> WriteResult:
    """HWPX 문서의 머리말/꼬리말을 설정합니다. None인 쪽은 건드리지 않습니다.

    Args:
        path: 원본 .hwpx 절대경로.
        header_text: 새 머리말.
        footer_text: 새 꼬리말.
        output_path: 결과를 쓸 경로. 생략하면 in_place=True가 필요합니다.
        overwrite: 출력 파일이 이미 있을 때 덮어쓰려면 True.
        in_place: output_path 없이 원본을 직접 수정하려면 True.
    """
    return set_header_footer_impl(
        path,
        header_text=header_text,
        footer_text=footer_text,
        output_path=output_path,
        overwrite=overwrite,
        in_place=in_place,
    )
