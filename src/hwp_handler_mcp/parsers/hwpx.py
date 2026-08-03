"""HWPX 파서 (python-hwpx 위임).

근거: .planning/research/RHWP-HWPX-PARSER.md, PYTHON-OSS.md.
"""

from __future__ import annotations

import logging

from hwpx import HwpxDocument
from hwpx.tools.text_extractor import TextExtractor

from hwp_handler_mcp.errors import ErrorCode, raise_hwp_error
from hwp_handler_mcp.ir import (
    Document,
    Format,
    Metadata,
    Paragraph,
    Run,
    Section,
    SecurityFlags,
)
from hwp_handler_mcp.parsers.opf import read_hwpx_package_metadata

log = logging.getLogger(__name__)


def parse_hwpx(path: str) -> Document:
    """HWPX 파일 → IR Document. python-hwpx에 텍스트 추출 위임."""
    try:
        doc = HwpxDocument.open(path)
    except Exception as exc:  # noqa: BLE001 — boundary catch
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"HWPX 파싱 실패: {exc}")

    try:
        sections = _build_sections(path)
        metadata = _extract_metadata(doc, section_count=len(sections), path=path)
        version = _read_version(doc)
    finally:
        doc.close()

    return Document(
        format=Format.HWPX,
        version=version,
        flags=SecurityFlags(),  # HWPX는 동등 비트 없음
        metadata=metadata,
        sections=sections,
    )


def _read_version(doc: HwpxDocument) -> str:
    """문서 버전 문자열. python-hwpx는 version 객체 노출 — string 변환."""
    try:
        ver = doc.version
        return str(ver) if ver is not None else "HWPX"
    except Exception:  # noqa: BLE001
        return "HWPX"


def _build_sections(path: str) -> tuple[Section, ...]:
    """python-hwpx의 TextExtractor로 paragraph 텍스트 추출 후 IR로 변환."""
    extractor = TextExtractor(path)
    out: list[Section] = []
    try:
        for section_info in extractor.iter_sections():
            paragraphs: list[Paragraph] = []
            for para_idx, para_info in enumerate(extractor.iter_paragraphs(section_info)):
                text = para_info.text()
                paragraphs.append(
                    Paragraph(
                        index=para_idx,
                        runs=(Run(text=text),) if text else (),
                    )
                )
            out.append(Section(index=section_info.index, paragraphs=tuple(paragraphs)))
    finally:
        extractor.close()
    return tuple(out)


def _extract_metadata(doc: HwpxDocument, *, section_count: int, path: str) -> Metadata:
    """HWPX 메타데이터 추출.

    OWPML 은 ``Contents/content.hpf`` 의 ``<opf:metadata>`` 에 제목/작성자/일시를
    담는다. python-hwpx 가 그대로 노출하지 않으므로 컨테이너에서 직접 읽는다.
    """
    raw: dict[str, str] = {}
    try:
        if hasattr(doc, "headers") and doc.headers:
            raw["headers_count"] = str(len(doc.headers))
    except Exception as exc:  # noqa: BLE001
        log.debug("HWPX 헤더 수 확인 실패: %s", exc)

    opf = read_hwpx_package_metadata(path)
    raw.update(opf.get("raw", {}))

    return Metadata(
        title=opf.get("title"),
        author=opf.get("author"),
        last_author=opf.get("last_author"),
        created_at=opf.get("created_at"),
        modified_at=opf.get("modified_at"),
        section_count=section_count,
        raw=raw,
    )
