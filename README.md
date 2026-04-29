# hwp-mcp

한글(HWP/HWPX) 문서를 읽기 위한 MCP(Model Context Protocol) 서버.

## 지원 포맷

- **HWP 5.x** (`.hwp`, OLE2 컨테이너) — 텍스트/표/메타데이터/첨부 + 사용자 비밀번호 복호화
- **HWPX** (`.hwpx`, OWPML/ZIP) — `python-hwpx` 위임
- **HWP 3.x** (한글 97/98) — best-effort, `hwplib-py` 검증 후 결정

## 보안 정책

- ✅ 사용자가 비밀번호를 알고 있는 문서의 정당한 복호화
- ❌ DRM 보호 문서 우회
- ❌ 한컴 ViewText(배포본) 보호 해제
- ❌ 비밀번호 무차별 대입

자세한 내용은 `.planning/requirements/REQUIREMENTS.md` §3.3 참조.

## 설치

```bash
uv venv .venv --python 3.11
uv sync
```

## 실행

```bash
uv run hwp-mcp           # stdio MCP 서버 시작
```

## Claude Code/Desktop 연결

`claude_desktop_config.json` 또는 Claude Code MCP 설정에 추가:

```json
{
  "mcpServers": {
    "hwp": {
      "command": "uv",
      "args": ["run", "--directory", "C:/Users/rudtn/mcp-servers/hwp", "hwp-mcp"],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

## 도구

- `detect_format` — 포맷/버전/보안 플래그 감지
- `extract_text` — 본문 텍스트 추출 (비번 입력 가능)
- `extract_metadata` — 제목/작성자/날짜
- `inspect_structure` — 컨테이너 구조 dump (분석용)
- `extract_tables` — 표 추출 (Phase B)
- `list_attachments` / `read_attachment` — 첨부 파일 (Phase B)

## 개발

```bash
uv run pytest                  # 테스트
uv run ruff check src tests    # 린트
uv run ruff format src tests   # 포매팅
uv run mypy src                # 타입 체크
```

## 라이선스

Apache-2.0

## 분석 자료

`.planning/research/` 아래에 rhwp(Rust) 파서 코드 분석 + Python OSS 생태계 조사 결과 보관.
