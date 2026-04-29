# hwp-mcp 코드 컨벤션

작성일: 2026-04-29
적용 범위: `src/hwp_mcp/`, `tests/`

---

## 1. Python 스타일

### 1.1 포매터 / 린터
- **포매터**: `ruff format` (Black 호환, 라인 100자)
- **린터**: `ruff check` — 룰셋: `E, W, F, I, N, B, UP, S, RET, SIM, PT`
- **타입체커**: `mypy --strict` (단계적 — `S, RET` 제외 가능)
- pre-commit 훅으로 강제

### 1.2 라인 길이
- 코드: 100자
- 주석/docstring: 100자 (한국어 가독성)
- 한국어 docstring은 의미 단위 줄바꿈 (마침표 기준)

### 1.3 타입 힌트 — **필수**
- 모든 public 함수/메서드에 인자/반환 타입 명시
- 내부 헬퍼도 권장 (mypy strict 통과 목표)
- `from __future__ import annotations` 파일 상단 (PEP 604 union 안전 사용)
- MCP 도구 함수는 **Pydantic BaseModel 반환** (FastMCP가 schema 자동 생성)

```python
# ✅ Good
@mcp.tool()
def extract_text(path: str, password: str | None = None) -> ExtractText:
    ...

# ❌ Bad — dict 반환은 schema 추론이 약함
def extract_text(path, password=None):
    return {...}
```

### 1.4 Naming
- 모듈/함수/변수: `snake_case`
- 클래스: `PascalCase`
- 상수: `UPPER_SNAKE`
- private: `_leading_underscore`
- MCP tool 이름: `snake_case` 동사+명사 (예: `extract_text`, `list_attachments`)
- 에러 코드 상수: `ERR_*` (예: `ERR_DRM_PROTECTED`)

### 1.5 한국어 / 영어 혼용
- **사용자 노출 메시지** (에러 메시지, 도구 description): 한국어 (사용자 환경)
- **코드 식별자, 로그, 커밋 메시지**: 영어
- **docstring**: 한국어 권장 (단, 변수명 영어와 자연스럽게)
- **주석**: 한국어 OK. 단, "WHY"만 적고 "WHAT" 금지

---

## 2. 프로젝트 구조

```
hwp-mcp/
├── pyproject.toml
├── uv.lock                 # 커밋
├── README.md
├── LICENSE                 # Apache-2.0
├── .gitignore
├── .python-version         # 3.11
├── src/
│   └── hwp_mcp/
│       ├── __init__.py     # 빈 파일 또는 __version__ 만
│       ├── __main__.py     # `python -m hwp_mcp`
│       ├── server.py       # FastMCP 인스턴스 + 도구 등록
│       ├── ir/             # 내부 표현
│       │   ├── __init__.py
│       │   ├── document.py # Document, Section, Paragraph, Run, ...
│       │   └── format.py   # FormatInfo, ErrorCode enum
│       ├── parsers/        # 포맷별 파서 (포맷 디스패치)
│       │   ├── __init__.py
│       │   ├── detect.py   # 4바이트 매직
│       │   ├── hwp5.py     # hwp-extract 위임 + 자체 record parser
│       │   ├── hwpx.py     # python-hwpx 위임
│       │   └── hwp3.py     # best-effort
│       ├── tools/          # MCP 도구 (얇은 wrapper)
│       │   ├── __init__.py
│       │   ├── text.py     # extract_text
│       │   ├── tables.py   # extract_tables
│       │   ├── metadata.py # extract_metadata
│       │   ├── attach.py   # list_attachments / read_attachment
│       │   └── inspect.py  # detect_format / inspect_structure
│       ├── errors.py       # McpError 헬퍼 + 에러 코드 enum
│       └── logging_setup.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/           # 샘플 .hwp / .hwpx (작은 것만)
│   ├── unit/
│   ├── integration/        # 실제 파서 호출
│   └── e2e/                # MCP stdio 호출 시뮬레이션
├── _external/              # 외부 분석 캐시 (rhwp/hop) — .gitignore
└── .planning/              # 설계 문서
```

### 2.1 의존 방향 (단방향)
```
tools/  →  parsers/  →  ir/, errors/
   ↓
server.py
```

- `ir/`은 의존 없음 (순수 dataclass)
- `parsers/`는 `ir/`만 import
- `tools/`는 `parsers/`, `ir/`, `errors/` import
- `server.py`는 `tools/`만 import (도구 등록)

### 2.2 책임 경계
- **parsers**: 포맷 → IR 변환만. MCP 알 필요 없음. 따라서 단위 테스트 쉬움
- **tools**: IR → MCP 응답(Pydantic 모델). 비즈니스 로직 없이 얇게
- **server**: 도구 등록 + transport (stdio) 시작

---

## 3. MCP 패턴

### 3.1 FastMCP 사용
- `mcp.server.fastmcp.FastMCP` 인스턴스 1개 (`server.py`)
- 도구 함수는 `tools/*.py`에 정의 후 `server.py`에서 `@mcp.tool()` 등록 또는 `mcp.add_tool()`

### 3.2 도구 함수 시그니처 규칙
- 첫 인자: 항상 `path: str` (절대경로)
- 비번 받을 때: `password: str | None = None`
- 페이징: `max_chars: int = 100_000`, `offset: int = 0`
- 반환: Pydantic BaseModel (절대 dict 직반환 금지)

### 3.3 에러 응답
```python
from hwp_mcp.errors import McpHwpError, ErrorCode

raise McpHwpError(
    code=ErrorCode.DRM_PROTECTED,
    message="DRM 보호 문서는 정책상 미지원",
    detail={"path": path},  # 선택적
)
```
- 메시지는 한국어
- `code`는 enum (REQUIREMENTS.md §3.3 매핑 그대로)
- `detail`에 path/version 등 진단 정보 (단, **password는 절대 포함 안 함**)

### 3.4 비동기 정책
- 기본은 **동기 함수**로 작성 (FastMCP가 알아서 처리)
- I/O 무거운 도구만 `async def` + `asyncio.to_thread(blocking_fn, ...)`
- 같은 모듈 안에서 sync/async 일관성 유지

### 3.5 큰 결과 처리
- 텍스트 결과 > `max_chars`: 잘라서 `truncated=True` + `next_offset` 반환
- 단일 첨부파일 > 5MB: 거부 + 상세 안내 (`ATTACHMENT_TOO_LARGE`)
- 추후 resource 노출은 Phase B 결정 (REQUIREMENTS.md §8 TBD)

---

## 4. 로깅

### 4.1 stdout 절대 금지
- `print()`, `sys.stdout.write` 사용 금지
- import 시 banner 찍는 라이브러리 의심 → import 후 stdout 위치 검증
- 테스트에서 `capfd`로 stdout 청결성 검증

### 4.2 logger 설정
```python
# logging_setup.py
import logging, sys, os

def setup_logging() -> None:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    level = os.environ.get("HWP_MCP_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```

### 4.3 로거 이름
- 모듈별: `logging.getLogger(__name__)` (예: `hwp_mcp.parsers.hwp5`)
- 절대 root logger에 직접 message X

### 4.4 비밀번호 누출 금지
- 비번 받는 함수는 로그 시 `password` 파라미터 마스킹
- repr/str에 비번 포함 안 되도록 dataclass 정의 시 `repr=False`

---

## 5. 에러 처리

### 5.1 정책
- **boundary에서 catch** — 도구 함수 외곽에서 `Exception` → `McpHwpError`로 변환
- 내부 코드에서는 raise만 하고 catch 최소화
- 절대 `except: pass` 금지 (`# noqa: E722`로도 안 됨)
- `except Exception as e: log.exception` 패턴은 boundary 1곳에서만

### 5.2 알 수 없는 레코드/태그
- **WARN 후 skip** (rhwp 패턴 답습)
- 일부 섹션 파싱 실패 시 가능한 만큼 반환 + `partial=True`
- 완전 실패 시 `INVALID_FORMAT` 에러

### 5.3 손상 파일
- `struct.error`, `zipfile.BadZipFile`, `lxml.etree.XMLSyntaxError` 등은 `INVALID_FORMAT`으로 변환
- 절대 traceback 그대로 사용자에게 노출 X (보안)

---

## 6. 테스트

### 6.1 구조
- `tests/unit/`: 순수 함수 단위 (IR 변환 로직, 매직 검사 등)
- `tests/integration/`: 실제 라이브러리 통합 (`hwp-extract`, `python-hwpx`)
- `tests/e2e/`: MCP stdio 시뮬레이션 (`mcp.shared.memory`로 in-process)

### 6.2 fixture 정책
- 작은 (< 100KB) 샘플만 git commit
- 큰 샘플은 `tests/fixtures/_external/` (gitignore) — `pytest --download-fixtures`로 옵트인
- 비밀번호 보호 샘플 1개 필수 (비번 = `test1234` 같은 단순값, 공개 OK)
- 손상 파일 샘플: 빈 파일, 잘못된 매직, 절단된 zip

### 6.3 mock 정책
- **mock 최소화** (회사 정책: feedback_avoid_mock 메모리)
- `hwp-extract` 같은 외부 라이브러리는 실제 호출
- 시간/난수만 mock 허용

### 6.4 stdout 청결성
```python
def test_no_stdout_pollution(capfd):
    from hwp_mcp.server import mcp
    out, _ = capfd.readouterr()
    assert out == "", f"stdout polluted: {out!r}"
```

### 6.5 커버리지 목표
- Phase A: 핵심 경로 80% 이상
- Phase B: 90% 이상
- 100%는 강요 안 함 (외부 라이브러리 wrapper 부분)

---

## 7. 의존성 / 패키지 관리

### 7.1 uv 사용
```bash
uv venv .venv --python 3.11
uv sync                  # pyproject.toml + uv.lock 기준
uv add <pkg>             # 새 의존 추가
uv run pytest            # 테스트
```

### 7.2 라이선스 게이트 (CI)
```bash
uv tree | grep -iE "AGPL|GPL-3" && exit 1
```
- pyhwp가 transitive로 끼어들면 즉시 빌드 실패

### 7.3 버전 핀 정책
- minor 단위 명시: `mcp[cli]>=1.27.0,<2.0.0`
- caret(^) 회피
- 보안 패치는 적극 따라가기

---

## 8. Git / 커밋 / PR

### 8.1 브랜치
- `main`: 안정 릴리즈
- `dev`: 통합
- `feat/<topic>`, `fix/<topic>`, `chore/<topic>`: 작업 브랜치

### 8.2 커밋 메시지 (Conventional Commits)
```
<type>(<scope>): <subject>

<body>
```
- type: feat, fix, refactor, test, docs, chore, perf
- scope: 모듈명 (예: `parsers/hwp5`, `tools/text`, `errors`)
- subject: 영어, 50자 이내, 명령형
- body: 한국어 OK, "WHY" 위주

### 8.3 PR 규칙
- 작은 단위 (≤ 500 LOC diff 권장)
- PR 본문에 변경 요약 + 검증 방법
- CI 통과 + 1 review approval 후 merge

---

## 9. 보안 / 라이선스

### 9.1 보안 코딩
- 사용자 입력 path는 `Path(path).resolve()` 후 사용
- 심볼릭 링크는 `Path.is_symlink()` 체크 후 거부 또는 경고
- 임시 파일은 `tempfile.NamedTemporaryFile(delete=True)` (절대 `/tmp/foo` 직접 X)
- subprocess 호출 시 `shell=False` + 인자 리스트

### 9.2 의존 라이선스
- 우리 코드: Apache-2.0
- 의존성: BSD/MIT/Apache 만 허용
- 신규 의존 추가 시 **반드시** PyPI 페이지에서 라이선스 확인 후 PR 본문에 명시

---

## 10. 회피 안티패턴 (Don'ts)

| ❌ 안티패턴 | ✅ 대체 |
|---|---|
| `print(...)` | `logger.info(...)` |
| `except: pass` | 명시적 예외 + 처리 또는 raise |
| dict 반환 from MCP tool | Pydantic BaseModel |
| password를 로그 / repr | 마스킹 |
| 상대경로 path 처리 | `Path(path).resolve()` |
| 장식적 conditional/mapped type | 단순 union 또는 dataclass |
| pyhwp / hwp-parser import | hwp-extract / hwplib-py 사용 |
| `os.system(cmd)` | `subprocess.run([...], shell=False)` |
| 큰 mock 트리 | 실제 라이브러리 호출 + 작은 fixture |
| 한 함수에 파싱 + 비즈니스 로직 | parsers/ vs tools/ 분리 |

---

## 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-04-29 | 초안 |
