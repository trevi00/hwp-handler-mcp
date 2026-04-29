"""HWPX 파서 (python-hwpx 위임).

근거: .planning/research/RHWP-HWPX-PARSER.md, PYTHON-OSS.md.
"""
from __future__ import annotations

import logging

from hwpx import HwpxDocument
from hwpx.tools.text_extractor import TextExtractor

from hwp_mcp.errors import ErrorCode, raise_hwp_error
from hwp_mcp.ir import (
    Document,
    Format,
    Metadata,
    Paragraph,
    Run,
    Section,
    SecurityFlags,
)

log = logging.getLogger(__name__)


def parse_hwpx(path: str) -> Document:
    """HWPX 파일 → IR Document. python-hwpx에 텍스트 추출 위임."""
    try:
        doc = HwpxDocument.open(path)
    except Exception as exc:  # noqa: BLE001 — boundary catch
        raise_hwp_error(ErrorCode.INVALID_FORMAT, detail=f"HWPX 파싱 실패: {exc}")

    try:
        sections = _build_sections(path)
        metadata = _extract_metadata(doc, section_count=len(sections))
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
            out.append(
                Section(index=section_info.index, paragraphs=tuple(paragraphs))
            )
    finally:
        extractor.close()
    return tuple(out)


def _extract_metadata(doc: HwpxDocument, *, section_count: int) -> Metadata:
    """문서 메타데이터 추출. rhwp는 안 읽지만 python-hwpx가 일부 노출."""
    raw: dict[str, str] = {}

    # python-hwpx가 어떤 메타를 노출하는지 best-effort로 시도
    # — package 객체에 manifest/spine 정보가 있고, 헤더 .xml에 begin numbers 등
    try:
        if hasattr(doc, "headers") and doc.headers:
            raw["headers_count"] = str(len(doc.headers))
    except Exception as exc:  # noqa: BLE001
        log.debug("HWPX 메타 추출 부분 실패: %s", exc)

    return Metadata(section_count=section_count, raw=raw)
