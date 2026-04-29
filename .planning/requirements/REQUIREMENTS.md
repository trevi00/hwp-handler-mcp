# hwp-mcp 요구사항

> **목표**: Claude Code/Desktop 등 MCP 클라이언트에서 한글(.hwp/.hwpx) 문서를 안전하고 정확하게 읽을 수 있는 자체 MCP 서버.

작성일: 2026-04-29
기준 분석 자료: `.planning/research/{RHWP-HWP5-PARSER, RHWP-HWPX-PARSER, RHWP-CRYPTO, PYTHON-OSS}.md`

---

## 1. 차별화 포지셔닝 (Why this MCP)

이미 존재하는 `hwpx-mcp-server` (airmang, HWPX-only)와 비교한 차별점:

| 영역 | hwpx-mcp-server | **hwp-mcp (우리)** |
|---|---|---|
| HWPX | ✅ 완전 | ✅ python-hwpx 위임 |
| HWP5 (.hwp 바이너리) | ❌ | ✅ **핵심** (hwp-extract + hwplib-py) |
| HWP3 (한글 97/98) | ❌ | △ best-effort (hwplib-py 부분 지원) |
| 사용자 비번 복호화 | ❌ | ✅ **핵심** (hwp-extract `--password` 위임) |
| DRM/배포본 우회 | — | ❌ **명시적 거부 (저작권법 준수)** |
| 표/이미지/메타데이터 추출 | ✅ | ✅ |

→ **차별 가치**: HWP5 + 비밀번호 복호화 + 통합 인터페이스(자동 포맷 감지).

---

## 2. 사용자 스토리

### 2.1 1차 사용자 — Claude Code/Desktop을 통해 HWP를 다루는 일반 사용자

- **US-1**: 사용자로서, 로컬에 있는 `.hwp` 또는 `.hwpx` 파일의 본문 텍스트를 한 번의 도구 호출로 추출하고 싶다 (RAG/요약/번역 입력으로 사용).
- **US-2**: 사용자로서, 비밀번호로 잠긴 HWP를 비밀번호와 함께 풀어 텍스트를 읽고 싶다.
- **US-3**: 사용자로서, 큰 문서를 페이지 단위 또는 chunk 단위로 잘라 받고 싶다 (LLM 컨텍스트 제한 회피).
- **US-4**: 사용자로서, 문서의 표(table)를 행/열 구조 그대로 추출해 받고 싶다 (Markdown table 또는 JSON).
- **US-5**: 사용자로서, 임베딩된 이미지/첨부 파일 목록과 메타(파일명/크기)를 보고 필요시 base64로 받고 싶다.
- **US-6**: 사용자로서, 작성자/제목/생성일 등 메타데이터를 빠르게 확인하고 싶다.

### 2.2 2차 사용자 — 보안/포렌식 분석가

- **US-7**: 분석가로서, 파일 자체를 변형하지 않고 구조(스트림 트리, 레코드 통계)를 dump해 보고 싶다.
- **US-8**: 분석가로서, 암호화/배포본/DRM/디지털서명/공개키 보호 여부 등 보안 플래그를 한눈에 보고 싶다.

### 2.3 비-사용자 (명시적 거부)

- **NU-1**: 한컴 발급 ViewText(배포용) 보호 해제 — 우회 안 함
- **NU-2**: DRM 보호 문서 우회 — 우회 안 함
- **NU-3**: 비밀번호 무차별 대입 / 사전공격 — 미구현
- **NU-4**: 키 추출/리버싱 — 미구현

---

## 3. MCP Tool 표면 (Surface)

FastMCP 기반. 모든 도구는 stdio JSON-RPC. 입력 path는 절대경로 권장.

### 3.1 핵심 도구

#### `detect_format(path: str) -> FormatInfo`
4바이트 매직으로 포맷 자동 감지.
```python
class FormatInfo(BaseModel):
    path: str
    format: Literal["hwp5", "hwpx", "hwp3", "unknown"]
    version: str | None       # 예: "5.1.0.0", "HWPX-2024"
    encrypted: bool
    distribution: bool        # ViewText 보호본
    drm: bool
    digital_signature: bool
    file_size: int
```

#### `extract_text(path, password=None, max_chars=100_000, offset=0) -> ExtractText`
본문 텍스트 추출. 표는 placeholder `[표 N]` 또는 별도 도구 사용.
```python
class ExtractText(BaseModel):
    text: str
    char_count: int
    truncated: bool           # max_chars로 잘렸는지
    next_offset: int | None   # 페이징용
    format: str               # "hwp5"|"hwpx"|"hwp3"
    section_count: int
    page_count: int | None    # HWPX에서만 신뢰 가능
```

#### `extract_tables(path, password=None) -> list[Table]`
모든 표를 행/열 매트릭스로 추출.
```python
class Table(BaseModel):
    section_index: int
    table_index: int          # 섹션 내 표 인덱스
    rows: int
    cols: int
    cells: list[list[str]]    # cells[row][col] = 셀 텍스트 (rowspan/colspan은 첫 칸에만)
    has_merged_cells: bool
    caption: str | None
```

#### `extract_metadata(path, password=None) -> Metadata`
작성자/제목/생성일 등.
```python
class Metadata(BaseModel):
    title: str | None
    author: str | None
    last_author: str | None
    created_at: str | None    # ISO8601
    modified_at: str | None
    company: str | None
    section_count: int
    page_count: int | None
    raw_summary: dict         # 그 외 헤더에서 뽑은 raw 키-값
```

#### `list_attachments(path, password=None) -> list[Attachment]`
임베딩 자산 목록(이미지, OLE 객체, 차트).
```python
class Attachment(BaseModel):
    storage_id: int           # HWP5의 BinData ID
    filename: str             # "BIN0001.png" 등
    media_type: str           # MIME 추정
    size_bytes: int
    is_image: bool
    is_ole: bool
```

#### `read_attachment(path, storage_id, password=None) -> AttachmentContent`
첨부 1개 base64로 반환.
```python
class AttachmentContent(BaseModel):
    storage_id: int
    filename: str
    media_type: str
    size_bytes: int
    content_base64: str       # base64 인코딩된 raw bytes
```

### 3.2 분석/디버깅 도구 (보안 분석가용)

#### `inspect_structure(path) -> StructureReport`
파일을 변형하지 않고 컨테이너 구조 dump.
```python
class StructureReport(BaseModel):
    format: str
    streams: list[StreamEntry]    # HWP5: OLE 스트림 목록 / HWPX: ZIP 엔트리 목록
    record_summary: dict[str, int] # 태그 ID → count
    flags: dict[str, bool]        # encrypted/distribution/drm 등
    warnings: list[str]           # 의심스러운 패턴
```

### 3.3 명시적 거부 케이스

호출 시 `McpError` + 한국어 메시지로 즉시 실패:

| 조건 | 에러 코드 | 메시지 |
|---|---|---|
| flags.distribution | `DISTRIBUTION_PROTECTED` | "한컴 배포용(ViewText) 보호 문서는 정책상 미지원" |
| flags.drm | `DRM_PROTECTED` | "DRM 보호 문서는 정책상 미지원" |
| flags.public_key_encrypted | `PKI_ENCRYPTED` | "공개키 암호화 문서는 미지원" |
| flags.encrypted + password 미입력 | `PASSWORD_REQUIRED` | "비밀번호로 보호된 문서. password 인자 필요" |
| password 입력 + 복호화 실패 | `WRONG_PASSWORD` | "비밀번호가 일치하지 않거나 지원하지 않는 암호 알고리즘" |
| 파일 매직 안 맞음 | `INVALID_FORMAT` | "HWP/HWPX 파일이 아님" |
| 파일 크기 초과 (예: 200MB) | `FILE_TOO_LARGE` | "파일이 너무 큼 (200MB 한도)" |
| ZipBomb 의심 | `ZIP_BOMB_SUSPECTED` | "압축 해제 결과가 한도 초과 (XML 32MB / BinData 64MB)" |

---

## 4. 비기능 요구사항

### 4.1 성능
- 1MB HWP5 텍스트 추출 < 500ms (warm)
- 10MB HWPX 텍스트 추출 < 3s
- 메모리 상한: 처리 중 파일 크기의 5배 이내

### 4.2 보안
- 압축 폭탄 방어 (rhwp 답습): XML 엔트리 32MB, BinData 64MB
- 파일 크기 상한 (기본 200MB)
- 절대경로만 허용 — 상대경로/심볼릭링크는 명시적 resolve 후 처리
- 비밀번호는 **로그에 절대 기록 안 함** (디버그 모드에서도)
- 사용자 입력 path가 시스템 디렉토리를 벗어나도록 강제하지 않음

### 4.3 신뢰성
- 손상된 파일도 panic 안 함 (`McpError`로 graceful)
- 알 수 없는 레코드 태그는 skip + warning (rhwp 패턴)
- 일부 섹션 파싱 실패 시 가능한 만큼만 반환 + `partial=True` 플래그

### 4.4 호환성
- Python 3.11 ~ 3.12 지원 (3.13은 lxml 빌드 이슈로 후순위)
- Windows 11 / macOS / Linux 모두 동작 (pure Python + wheel 의존만)
- Claude Desktop, Claude Code, MCP Inspector에서 검증

### 4.5 로깅
- 모든 로그 → `stderr`만 (stdout은 JSON-RPC 전용)
- `PYTHONIOENCODING=utf-8` + `sys.stderr.reconfigure(encoding='utf-8')` 적용
- 로그 레벨: 기본 WARNING, `HWP_MCP_LOG_LEVEL` env로 조정

### 4.6 라이선스
- 우리 코드: **Apache-2.0** (의존성과 호환)
- AGPL 라이브러리 의존 금지 (pyhwp 등)
- `uv tree | grep -i agpl` 검사를 CI에서 수행

---

## 5. 의존성 정책 (재확인)

`.claude/tech-stack.yaml` 참조. 핵심:
- **사용**: `mcp[cli]`, `python-hwpx`, `hwp-extract`, `hwplib-py`, `olefile`, `lxml`
- **회피**: `pyhwp` (AGPL), `pyhwpx` (COM 의존), `hwp-parser` (AGPL 전파)
- **참고만**: `rhwp` (Rust, 스펙 정오표 추출)

`hwplib-py`는 라이선스/유지보수 상태가 불확실 — **첫 통합 PR 전에 검증 필수**:
1. PyPI 페이지에서 라이선스 확인
2. 실제 import 후 HWP3/HWP5 샘플 파싱 테스트
3. 실패 시: HWP5는 hwp-extract + 자체 record parser, HWP3는 scope 제외

---

## 6. 단계별 우선순위 (MVP → 확장)

### Phase A — MVP (스코프 확정)
1. `detect_format` (4바이트 매직)
2. `extract_text` for HWPX (python-hwpx 위임)
3. `extract_text` for HWP5 (hwp-extract 또는 자체 olefile+zlib+struct 경로)
4. `extract_metadata` (HWPX/HWP5 둘 다, best-effort)
5. 보안 플래그 검사 + 명시적 거부 케이스
6. stdio MCP 서버 + Claude Code 연결 검증

### Phase B — 확장
7. `extract_tables`
8. 비밀번호 복호화 (`extract_text(password=...)`)
9. `list_attachments` / `read_attachment`
10. `inspect_structure` (분석가용)
11. 페이징 (`max_chars` + `offset`)

### Phase C — 후순위
12. HWP3 best-effort (hwplib-py 검증 후)
13. Markdown export (python-hwpx의 `export_markdown` 통합)
14. 표 → Markdown 자동 변환

---

## 7. 검증 기준 (Acceptance)

### Phase A 통과 조건
- [ ] HWPX 샘플 5개에서 본문 텍스트 추출 (한글/영문/숫자/특수문자 모두)
- [ ] HWP5 샘플 5개에서 본문 텍스트 추출
- [ ] 빈 파일/손상 파일 → graceful error
- [ ] DRM/배포본 → 즉시 거부 + 명확한 한국어 에러 메시지
- [ ] Claude Code에서 도구 호출 → 응답 정상 표시
- [ ] stdout에 print 누출 0건 (CI 검사)
- [ ] `uv tree`에 AGPL 라이브러리 0개

### Phase B 추가
- [ ] 표 1행/열 추출 정확도 ≥ 95% (5개 샘플 기준)
- [ ] 비번 정상 입력 → 복호화 성공
- [ ] 비번 오답 → `WRONG_PASSWORD` 즉시
- [ ] 1MB → 100MB 파일 메모리 5배 이내

---

## 8. 미해결 결정 사항 (TBD — 다음 단계에서 확정)

1. **표 placeholder 표기 형식** — `[표 N]` vs `<TABLE id="N"/>` vs Markdown table 인라인. → MCP-API 설계 단계에서 확정
2. **chunk/페이징 단위** — 문자 수 기준 vs 단락 수 기준 vs 페이지 기준. → 같은 단계
3. **HWP3 scope** — 완전 제외 vs hwplib-py 검증 후 결정. → hwplib-py 라이선스 확인 후
4. **로그 파일 vs stderr only** — 일부 사용자는 파일 로그 선호. → 환경변수 옵션 추가 검토
5. **resource 노출 vs tool only** — 큰 결과를 MCP resource(`hwp://`)로 노출할지. → 사용 패턴 보고 Phase B에서 결정

---

## 9. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-04-29 | 초안. 4개 분석(rhwp HWP5/HWPX/Crypto + Python OSS) 통합 |
