# Python HWP 생태계 + MCP Python SDK 베스트 프랙티스

조사일: 2026-04-29

---

## 1. Python HWP 파싱 라이브러리 비교

### 1.1 HWP5 (binary, OLE2) 계열

#### pyhwp (mete0r) — **회피 권장**
- PyPI: `pyhwp` 0.1b15 (2020-05-30). GitHub 1,551 commits, 295 stars. **inactive (>6개월 무커밋)**
- 라이선스: **AGPLv3+** ← 서비스 배포 시 소스 공개 의무
- 지원: HWP5만
- Python: 2.7, 3.5–3.8 공식. 3.9+ 미테스트
- CLI: `hwp5proc`, `hwp5txt`, `hwp5html`, `hwp5odt`
- 암호: `hwp5proc diststream`이 분산 키만 토해냄. **사용자 비번 → 키 변환 흐름 미노출** (Issue #154 미해결)

#### hwplib-py
- PyPI: `hwplib-py` 1.0.0
- 성격: pure Python HWP5 파서. **HWP3 records 부분 지원 명시** ← 본 조사에서 유일하게 HWP3 언급
- 의존: olefile + zlib
- 라이선스/암호 지원: PyPI 페이지 접속 에러 → **도입 전 직접 확인 필요**

#### libhwp
- PyPI: `libhwp` 0.2.0 (2022-11-11), Apache-2.0
- 구현: **Rust + maturin 바인딩**. 사전컴파일 wheels (Windows/Linux/macOS)
- API: `find_all('paragraph'|'table'|'caption'|'equation'|'footnote'|'endnote')`
- 유지보수: 2022년 이후 릴리즈 없음 → semi-inactive

#### hwp-extract (Volexity) — **암호 복호화 핵심**
- PyPI: `hwp-extract` 0.1.0 (2024-11-27), **BSD-3-Clause**
- Python: 3.9–3.12
- 메인테이너: Volexity (보안 분석 회사) — 포렌식·악성문서 분석 목적
- CLI: `hwp-extract <file> --extract-files --extract-meta --password <PW>` ← **사용자 비번 직접 입력 지원 (조사된 OSS 중 유일)**
- 한계: 객체/메타 추출 위주. 본문 텍스트 구조적 추출(문단/표/스타일)은 약함

### 1.2 HWPX (ZIP + XML) 계열

#### python-hwpx (airmang) — **HWPX best-in-class**
- PyPI: `python-hwpx` v2.9.1 (2026-04-27), **Apache-2.0**
- Python: 3.10+. 의존: `lxml >= 4.9` 만
- 구현: pure Python. 한컴오피스 설치 불필요
- 기능: read/edit/generate/validate. `export_text/export_markdown`, OPC validator, 스키마 validator
- CLI: `hwpx-validate`, `hwpx-validate-package`, `hwpx-analyze-template`
- 유지보수: 매우 활발 (v2.x 시리즈 진행 중)
- 암호: **encrypted HWPX 명시적 미지원**
- **부가 자산: `hwpx-mcp-server` 별도 레포 + `hwpx-skill` agent skill** ← 우리 MCP의 직접 경쟁자/참고대상

#### gethwp / airun-hwp / hwp-hwpx-parser
- gethwp: 가벼운 텍스트 추출 래퍼, 활성도 낮음
- airun-hwp: HWP/HWPX → Markdown/PDF 변환 툴 (파서 아님). 의존 무거움
- hwp-hwpx-parser: 정보 미확인

#### pyhwpx — **MCP에 부적합**
- pywin32 COM 자동화 래퍼 — Windows 전용 + Hancom Office 설치 필수

### 1.3 HWP3 (한글 97/98)

- 전용 라이브러리 **사실상 없음**
- `hwplib-py`만 "HWP3 records 부분 지원" 표기. 깊이는 미검증
- 결론: HWP3는 OSS 공백 영역. 한국 현장 빈도 매우 낮음 (한컴 자체 변환기로 마이그레이션된 지 20년)

### 1.4 일반 컨테이너

#### olefile
- PyPI: `olefile` 0.47, BSD, 의존성 없음
- HWP5 = OLE2 → 스트림 열거/읽기 가능. 레코드 파싱은 별도 구현 필요
- 역할: 저수준 디버깅용 fallback

---

## 2. 권장 조합 (Recommendation Matrix)

| 책임 | 후보 | 추천 | 이유 |
|---|---|---|---|
| HWP5 컨테이너 + 암호 | olefile / pyhwp / hwp-extract | **hwp-extract** + olefile fallback | BSD-3, 비번 지원 |
| HWP5 레코드 파싱 | pyhwp / hwplib-py / libhwp | **hwplib-py** (검증 후) → libhwp fallback | pyhwp는 AGPL. hwplib-py는 pure Python + HWP3 일부 |
| HWPX 전 영역 | zipfile+lxml / python-hwpx / gethwp | **python-hwpx (airmang)** | Apache-2.0, 활발, validator 풍부 |
| HWP3 | hwplib-py 외 없음 | **scope 제외 + best-effort** | v1은 "HWP3 미지원, hwp-extract로 메타만 시도" 정책 |
| 암호 복호화 | pyhwp / hwp-extract / cryptography 직접 | **hwp-extract --password 위임** | 유일하게 사용자 비번 받는 OSS API. 직접 구현은 2-Strike 회피 |
| 텍스트 추출 (RAG/요약) | hwp-parser (LangChain) / 자체 wrapper | **자체 thin wrapper** | hwp-parser는 pyhwp(AGPL) 의존 |
| HWP/HWPX 자동 판별 | 시그니처 검사 | **자체 4바이트 매직 검사** | D0CF11E0 → OLE2/HWP5, 504B0304 → ZIP/HWPX |

### 추천 의존성 트리 (최소셋)

```toml
dependencies = [
    "mcp[cli]>=1.27.0,<2.0.0",      # MCP SDK (FastMCP 포함)
    "python-hwpx>=2.9.0",            # HWPX 전 영역
    "hwp-extract>=0.1.0",            # HWP5 + 암호 복호화
    "hwplib-py>=1.0.0",              # HWP5 레코드 깊은 파싱 (검증 후)
    "olefile>=0.47",                 # 저수준 OLE2 fallback
    "lxml>=4.9",                     # XML
]
```

### 라이선스 매트릭스 (배포 관점)

| 라이브러리 | 라이선스 | MCP에서 OK? |
|---|---|---|
| python-hwpx | Apache-2.0 | ✅ |
| hwp-extract | BSD-3 | ✅ |
| hwplib-py | 미확인 → 도입 전 확인 | TBD |
| olefile | BSD | ✅ |
| libhwp | Apache-2.0 | ✅ |
| **pyhwp** | **AGPLv3+** | ❌ **회피 권장** |
| pyhwpx (COM) | 미확인 + Windows/Hancom 종속 | ❌ |

---

## 3. MCP Python SDK 패턴

공식 SDK: `modelcontextprotocol/python-sdk`. PyPI `mcp` 1.27.0 (2026-04-02). FastMCP 1.0이 SDK에 흡수됨.

### 3.1 FastMCP vs 저수준 Server

| 항목 | FastMCP | low-level Server |
|---|---|---|
| 코드량 | 데코레이터, 최소 | handler 직접 구현, 장황 |
| 스키마 | 타입힌트 → 자동 (Pydantic) | 직접 작성 |
| 적합 | **우리 케이스 (정적 도구 5–20개)** | 동적 도구, 외부 백엔드 프록시 |

→ **FastMCP 채택**. parse, extract_text, extract_tables, decrypt 등 정적 셋.

### 3.2 권장 골격

```python
from mcp.server.fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS
from pydantic import BaseModel, Field

mcp = FastMCP("hwp-mcp")

class ExtractResult(BaseModel):
    text: str
    page_count: int = Field(description="문서 총 페이지 수")
    truncated: bool

@mcp.tool()
def extract_text(path: str, password: str | None = None, max_chars: int = 100_000) -> ExtractResult:
    """HWP/HWPX 파일에서 본문 텍스트를 추출한다."""
    if not path:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="path required"))
    return ExtractResult(text=..., page_count=..., truncated=...)

if __name__ == "__main__":
    mcp.run()  # 기본 stdio
```

### 3.3 핵심 결정 사항

- **async 의무?** No. 단 무거운 I/O는 `async def` + `asyncio.to_thread`로 blocking 라이브러리 감싸기
- **transport**: Claude Code/Desktop 연결은 **stdio 표준**. SSE/Streamable HTTP는 원격 멀티유저용
- **에러 응답**: `McpError(ErrorData(code=..., message=...))`. v2부터 `MCPError`로 변경 예정 — import를 한 곳에 모아두면 마이그레이션 1줄
- **구조화 출력**: 리턴 타입이 BaseModel/TypedDict/dataclass면 자동 schema. 명시적 모델 권장
- **큰 결과 처리** (전체 문서 텍스트):
  - 대안 1: `max_chars` 파라미터 + `truncated` 플래그 + `offset`으로 재호출
  - 대안 2: **resource로 노출** — `hwp://session/<id>/text` URI + cursor 페이지네이션
  - 대안 3: 임시 파일 경로 리턴 ("<path>에 저장됨")

### 3.4 로깅·진단

- **stdout = JSON-RPC 전용. print 절대 금지**. 로그는 반드시 `stderr`
- 한국어 로그 + Windows cp949 콘솔 충돌 방지: `sys.stderr.reconfigure(encoding='utf-8')` + `PYTHONIOENCODING=utf-8`

---

## 4. 의존성 관리

### 4.1 패키지 매니저

- **uv (Astral) 권장** — MCP 생태계 사실상 표준
- **`mcp[cli]` extra 필수** — `mcp` CLI 포함 (hot reload, Claude Desktop 등록)

### 4.2 Python 버전

- **Python 3.11 권장** (안정). 3.13은 lxml 빌드 이슈 가능

### 4.3 Windows 빌드

- lxml 5.x: Windows wheel 모두 PyPI에 있음. 컴파일 안 함
- olefile, hwp-extract, python-hwpx: pure Python, 빌드 이슈 없음
- libhwp: Rust → 사전컴파일 wheel

### 4.4 caret(^) 범위 회피

SDK가 minor에 breaking patch 낸 전례 있음. `>=1.27,<2.0` 식 명시 핀 권장. `uv.lock` 커밋.

---

## 5. 발견한 위험·함정

### 5.1 라이선스 폭탄

- **pyhwp = AGPLv3+** ← MCP 서버 배포 시 소스 공개 의무 발동 가능
- hwp-parser, pyhwp2 등 파생물도 동일 전파. `uv tree | grep pyhwp` 검사 권장

### 5.2 암호 복호화의 현실

- 사용자 비번 → 복호화 인터페이스가 명시 노출된 OSS는 **hwp-extract 단 하나**
- HWPX 암호화는 OSS 전부 미지원
- 전략: hwp-extract에 비번 위임 + 실패 시 명확히 "지원 안 됨" 에러

### 5.3 한글 인코딩 함정

- HWP5 내부 = UTF-16LE. 직접 olefile로 스트림 열 때는 명시 디코드 필요
- Windows 콘솔 cp949 ↔ Python UTF-8 충돌:
  - MCP stdio 통신 자체는 JSON-RPC ASCII safe
  - logging stderr 한글 출력 시 `UnicodeEncodeError` 다발 → `PYTHONIOENCODING=utf-8` + `sys.stderr.reconfigure`

### 5.4 stdio 통신 함정

- stdout에 print 금지 — JSON-RPC 깨짐
- 일부 라이브러리 import 시점 stdout banner 주의
- subprocess 실행 시 cwd 임의 → **항상 절대 경로**

### 5.5 HWP 포맷 자체 함정

- HWP5 안 임베디드 OLE 객체 (Excel 표, 그림) 흔함 → 텍스트 누락 또는 garbage 섞임
- HWPX는 ZIP인데 store(비압축)+deflated 혼합 → OPC 무결성 검사 필수. python-hwpx의 `hwpx-validate-package` 게이트 사용 권장
- **표 셀 줄바꿈** — 단순 `\n` join으로 표 망가짐. `extract_tables` 별도 도구 + `extract_text`는 표를 `[표 1]` placeholder

### 5.6 의존성 트리 충돌

- python-hwpx + hwp-extract 둘 다 lxml 의존 → uv.lock으로 단일 버전 강제

### 5.7 경쟁자 인지

- **`hwpx-mcp-server` (airmang)가 이미 존재** — python-hwpx 저자가 직접 운영
- **우리 MCP의 차별점이 명확해야 함**:
  1. HWP5 텍스트/메타/표 추출 (hwplib-py + hwp-extract)
  2. **암호 문서 복호화** (hwp-extract --password 위임) ← airmang 미지원
  3. HWPX (python-hwpx 위임 — wrapping만)
  4. HWP3 (best-effort, "지원 제한적" 명시)

---

## Sources

- pyhwp: https://pypi.org/project/pyhwp/, https://github.com/mete0r/pyhwp
- pyhwp Issue #154 (decrypt): https://github.com/mete0r/pyhwp/issues/154
- olefile: https://pypi.org/project/olefile/
- python-hwpx: https://github.com/airmang/python-hwpx
- hwp-extract: https://pypi.org/project/hwp-extract/, https://github.com/volexity/hwp-extract
- libhwp: https://pypi.org/project/libhwp/
- hwplib-py: https://libraries.io/pypi/hwplib-py
- mcp Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP build-server docs: https://modelcontextprotocol.io/docs/develop/build-server
- uv: https://docs.astral.sh/uv/
- lxml install: https://lxml.de/installation.html
