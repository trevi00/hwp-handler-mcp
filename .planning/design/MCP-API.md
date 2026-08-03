# hwp-handler-mcp MCP API 설계

작성일: 2026-04-29
근거: REQUIREMENTS.md §3, FORMAT-IR.md, PYTHON-OSS.md §3

> **목표**: MCP 클라이언트(Claude Code/Desktop)가 호출하는 도구 7종의 입출력 schema, 에러 응답, 사용 예시를 확정한다.

---

## 1. 공통 규약

### 1.1 transport
- stdio (JSON-RPC 2.0)
- 서버 등록 이름: `hwp-handler-mcp`

### 1.2 입력 공통
- `path: str` — **절대경로 권장**. 상대경로는 `Path.cwd()`로 resolve. UNC/심볼릭 링크는 거부 또는 재해석
- `password: str | None = None` — 비번 보호 문서 전용
- 모든 string은 UTF-8 (한국어 path/비번 OK)

### 1.3 응답 공통 필드
모든 도구 응답에 다음 메타 포함:
```python
class _Meta(BaseModel):
    elapsed_ms: int                # 처리 시간
    warnings: list[str] = []       # 부분 파싱 경고
```
응답 모델은 `_Meta`를 inline으로 합쳐 평탄화.

### 1.4 에러 형식
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "비밀번호가 일치하지 않거나 지원하지 않는 암호 알고리즘",
    "data": {
      "code": "WRONG_PASSWORD",
      "path": "C:/docs/secret.hwp",
      "format_detected": "hwp5"
    }
  }
}
```
- `data.code`: REQUIREMENTS.md §3.3의 에러 코드 enum
- `data` 필드에는 **password 절대 포함 안 함**

---

## 2. 도구 목록

| 도구 | Phase | 입력 핵심 | 반환 핵심 |
|---|---|---|---|
| `detect_format` | A | path | format/version/flags |
| `extract_text` | A | path, password?, max_chars, offset | text + truncated + next_offset |
| `extract_metadata` | A | path, password? | title/author/created_at... |
| `inspect_structure` | A | path | streams + record_summary + flags |
| `extract_tables` | B | path, password? | list[Table] |
| `list_attachments` | B | path, password? | list[Attachment metadata] |
| `read_attachment` | B | path, storage_id, password? | base64 content |

---

## 3. `detect_format`

### 3.1 입력
```python
class DetectFormatInput(BaseModel):
    path: str = Field(description="HWP 또는 HWPX 파일 절대경로")
```

### 3.2 출력
```python
class FormatInfo(BaseModel):
    path: str
    format: Literal["hwp5", "hwpx", "hwp3", "unknown"]
    version: str | None
    encrypted: bool
    distribution: bool
    drm: bool
    digital_signature: bool
    public_key_encrypted: bool
    script: bool
    file_size: int
    elapsed_ms: int
    warnings: list[str] = []
```

### 3.3 동작
1. 파일 4바이트 매직 검사:
   - `D0 CF 11 E0` → OLE2 → HWP5 또는 HWP3 (FileHeader 시그니처로 구분)
   - `50 4B 03 04` → ZIP → HWPX 가능성. `mimetype` 또는 `Contents/content.hpf` 존재 시 HWPX
2. HWP5: FileHeader.flags 32비트 → SecurityFlags 매핑
3. HWPX: `Contents/content.hpf` 만 열고 spine 카운트. 보안 플래그 모두 False (HWPX 자체에 동등 비트 없음)
4. unknown: 4바이트가 매칭 안 되면 `format="unknown"`

### 3.4 예시
```json
// 입력
{ "path": "C:/docs/sample.hwp" }

// 출력
{
  "path": "C:/docs/sample.hwp",
  "format": "hwp5",
  "version": "5.1.0.0",
  "encrypted": false,
  "distribution": false,
  "drm": false,
  "digital_signature": false,
  "public_key_encrypted": false,
  "script": false,
  "file_size": 184320,
  "elapsed_ms": 5,
  "warnings": []
}
```

### 3.5 에러
| 코드 | 조건 |
|---|---|
| `FILE_NOT_FOUND` | path 존재 안 함 |
| `FILE_TOO_LARGE` | 200MB 초과 |
| `PERMISSION_DENIED` | 읽기 권한 없음 |

---

## 4. `extract_text`

### 4.1 입력
```python
class ExtractTextInput(BaseModel):
    path: str = Field(description="HWP/HWPX 파일 절대경로")
    password: str | None = Field(default=None, description="비밀번호 보호 문서의 비밀번호")
    max_chars: int = Field(default=100_000, ge=1, le=2_000_000, description="결과 텍스트 최대 문자 수")
    offset: int = Field(default=0, ge=0, description="이전 호출에서 받은 next_offset 값")
    include_tables: bool = Field(default=False, description="True면 표를 Markdown으로 인라인. False면 [표 N] placeholder")
    include_images: bool = Field(default=False, description="True면 이미지 위치에 [이미지] 마커")
```

### 4.2 출력
```python
class ExtractText(BaseModel):
    text: str
    char_count: int                # 반환된 text의 문자 수
    total_char_count: int          # 전체 문서 문자 수 (예측치 OK)
    truncated: bool
    next_offset: int | None        # truncated=True일 때만 의미 있음
    format: Literal["hwp5", "hwpx", "hwp3"]
    section_count: int
    page_count: int | None
    partial: bool                  # 부분 파싱 여부
    elapsed_ms: int
    warnings: list[str] = []
```

### 4.3 동작
1. `detect_format` 등가 로직으로 포맷/플래그 검사
2. 거부 케이스 (DRM/distribution/PKI) → 즉시 McpError
3. `encrypted` + `password` 없음 → `PASSWORD_REQUIRED`
4. 포맷별 파서 위임:
   - HWPX → `python-hwpx` 또는 자체 lxml
   - HWP5 + 비번 → `hwp-extract --password` 위임
   - HWP5 일반 → 자체 olefile 경로 + (옵션) hwplib-py
   - HWP3 → hwplib-py (실패 시 partial)
5. IR 생성 → `document_to_text(doc, include_tables, ...)`
6. `[offset:offset+max_chars]`로 자름
7. `next_offset` 계산

### 4.4 예시
```json
// 입력
{ "path": "C:/docs/sample.hwp", "max_chars": 5000 }

// 출력 (Phase A 응답)
{
  "text": "제목\n\n본문 첫 단락...\n[표 1]\n다음 단락...",
  "char_count": 4823,
  "total_char_count": 18450,
  "truncated": true,
  "next_offset": 4823,
  "format": "hwp5",
  "section_count": 1,
  "page_count": null,
  "partial": false,
  "elapsed_ms": 142,
  "warnings": []
}
```

### 4.5 에러 — REQUIREMENTS.md §3.3 표 참조

추가:
| 코드 | 조건 |
|---|---|
| `OFFSET_OUT_OF_RANGE` | offset > 전체 문자 수 |

---

## 5. `extract_metadata`

### 5.1 입력
```python
class ExtractMetadataInput(BaseModel):
    path: str
    password: str | None = None
```

### 5.2 출력
```python
class Metadata(BaseModel):
    format: Literal["hwp5", "hwpx", "hwp3"]
    title: str | None = None
    author: str | None = None
    last_author: str | None = None
    created_at: str | None = None      # ISO8601
    modified_at: str | None = None
    company: str | None = None
    section_count: int = 0
    page_count: int | None = None
    raw: dict[str, str] = {}           # 그 외 헤더에서 뽑은 raw key→value
    elapsed_ms: int
    warnings: list[str] = []
```

### 5.3 동작
- HWPX: `Contents/content.hpf` `<opf:metadata>` (Dublin Core) + `header.xml` `<hh:beginNum>`
- HWP5: `hwp-extract --extract-meta` 결과 또는 직접 OLE `\005SummaryInformation` 읽기
- HWP3: best-effort

---

## 6. `inspect_structure`

### 6.1 입력
```python
class InspectStructureInput(BaseModel):
    path: str
    include_data_preview: bool = False  # True면 각 스트림 첫 64바이트 hex
```

### 6.2 출력
```python
class StreamEntry(BaseModel):
    name: str            # OLE 경로 또는 ZIP 엔트리
    size: int
    compressed_size: int | None  # ZIP만
    sha256: str          # 무결성 검증용
    preview_hex: str | None      # include_data_preview=True 시

class StructureReport(BaseModel):
    path: str
    format: str
    streams: list[StreamEntry]
    record_summary: dict[str, int]   # tag_id 16진 → 개수
    flags: dict[str, bool]
    warnings: list[str]
    elapsed_ms: int
```

### 6.3 동작
- 파일을 변형하지 않음 (read-only)
- HWP5: olefile로 스트림 트리 + DocInfo/BodyText의 record tag 카운트
- HWPX: zipfile로 엔트리 트리 + 각 XML root tag 카운트

### 6.4 보안 분석가 시나리오
- 비정상 스트림 감지 (예: `Scripts/` 비어있는데 script 플래그 켜짐)
- 알려지지 않은 record tag → 의심 라벨

---

## 7. `extract_tables` (Phase B)

### 7.1 입력
```python
class ExtractTablesInput(BaseModel):
    path: str
    password: str | None = None
    section_index: int | None = None   # None이면 전체
```

### 7.2 출력
```python
class TableExtract(BaseModel):
    section_index: int
    table_index: int
    rows: int
    cols: int
    cells: list[list[str]]            # cells[row][col] (병합셀은 첫 칸만 텍스트)
    spans: list[list[tuple[int, int]]] | None  # (row_span, col_span)
    has_merged_cells: bool
    caption: str | None

class ExtractTablesResult(BaseModel):
    tables: list[TableExtract]
    total_count: int
    elapsed_ms: int
    warnings: list[str] = []
```

---

## 8. `list_attachments` (Phase B)

### 8.1 입력
```python
class ListAttachmentsInput(BaseModel):
    path: str
    password: str | None = None
```

### 8.2 출력
```python
class AttachmentInfo(BaseModel):
    storage_id: str           # HWP5: "BIN0001", HWPX: href
    filename: str
    media_type: str
    size_bytes: int
    is_image: bool
    is_ole: bool

class ListAttachmentsResult(BaseModel):
    attachments: list[AttachmentInfo]
    total_count: int
    total_size_bytes: int
    elapsed_ms: int
    warnings: list[str] = []
```

---

## 9. `read_attachment` (Phase B)

### 9.1 입력
```python
class ReadAttachmentInput(BaseModel):
    path: str
    storage_id: str
    password: str | None = None
    max_size_bytes: int = Field(default=5_242_880, description="기본 5MB")
```

### 9.2 출력
```python
class AttachmentContent(BaseModel):
    storage_id: str
    filename: str
    media_type: str
    size_bytes: int
    content_base64: str
    elapsed_ms: int
    warnings: list[str] = []
```

### 9.3 에러
| 코드 | 조건 |
|---|---|
| `ATTACHMENT_NOT_FOUND` | storage_id 없음 |
| `ATTACHMENT_TOO_LARGE` | size > max_size_bytes |

---

## 10. 에러 코드 사전

| 코드 (`data.code`) | HTTP-equivalent 의미 | 메시지 (한국어) |
|---|---|---|
| `FILE_NOT_FOUND` | 404 | "파일을 찾을 수 없습니다: {path}" |
| `FILE_TOO_LARGE` | 413 | "파일이 너무 큼 ({size}B, 한도 200MB)" |
| `PERMISSION_DENIED` | 403 | "파일 읽기 권한이 없습니다" |
| `INVALID_FORMAT` | 415 | "HWP/HWPX 파일이 아니거나 손상됨" |
| `UNSUPPORTED_VERSION` | 422 | "지원하지 않는 HWP 버전: {version}" |
| `PASSWORD_REQUIRED` | 401 | "비밀번호로 보호된 문서. password 인자 필요" |
| `WRONG_PASSWORD` | 401 | "비밀번호가 일치하지 않거나 지원하지 않는 암호 알고리즘" |
| `DISTRIBUTION_PROTECTED` | 451 | "한컴 배포용(ViewText) 보호 문서는 정책상 미지원" |
| `DRM_PROTECTED` | 451 | "DRM 보호 문서는 정책상 미지원" |
| `PKI_ENCRYPTED` | 422 | "공개키 암호화 문서는 미지원" |
| `ZIP_BOMB_SUSPECTED` | 413 | "압축 해제 결과가 한도 초과" |
| `OFFSET_OUT_OF_RANGE` | 416 | "offset이 전체 텍스트 범위 초과" |
| `ATTACHMENT_NOT_FOUND` | 404 | "첨부 파일을 찾을 수 없습니다: {storage_id}" |
| `ATTACHMENT_TOO_LARGE` | 413 | "첨부 파일이 너무 큼 ({size}B, 한도 {max}B)" |
| `PARTIAL_PARSE_FAILED` | 500 | "파일을 부분 파싱할 수 없습니다" |
| `INTERNAL_ERROR` | 500 | "내부 오류 — 자세한 내용은 로그 참조" |

→ Python에서 `class ErrorCode(str, Enum): ...`로 정의 (`src/hwp_handler_mcp/errors.py`).

---

## 11. 사용 시나리오 (Claude Code에서)

### 11.1 단순 텍스트 추출
```
사용자: "C:/docs/회의록.hwp 본문 요약해줘"
Claude: detect_format → extract_text → 요약
```

### 11.2 비밀번호 보호 문서
```
사용자: "C:/docs/secret.hwp 열어봐. 비번은 1234"
Claude: detect_format (encrypted=true) → extract_text(password="1234")
```

### 11.3 표 분석
```
사용자: "이 문서의 표만 따로 보여줘"
Claude: extract_tables → JSON 또는 Markdown 변환 응답
```

### 11.4 보안 분석
```
사용자: "이 hwp 파일 의심스러운데, 구조 분석해줘"
Claude: inspect_structure(include_data_preview=True) → 보고
```

---

## 12. 도구 description (사용자 노출 — 한국어)

각 도구의 `description=` 필드에 들어갈 짧은 설명:

| 도구 | description |
|---|---|
| `detect_format` | "HWP/HWPX 파일의 포맷, 버전, 보안 플래그(암호/DRM/배포)를 감지합니다." |
| `extract_text` | "HWP/HWPX 본문 텍스트를 추출합니다. 비밀번호 보호 문서는 password 인자로 풀 수 있습니다." |
| `extract_metadata` | "문서의 제목, 작성자, 생성일 등 메타데이터를 추출합니다." |
| `inspect_structure` | "파일을 변형하지 않고 컨테이너 구조(스트림/엔트리/레코드)를 dump합니다. 포렌식 분석용." |
| `extract_tables` | "문서 안의 모든 표를 행/열 구조로 추출합니다." |
| `list_attachments` | "임베딩된 이미지/OLE 객체/차트 목록을 반환합니다." |
| `read_attachment` | "특정 첨부 파일의 내용을 base64로 반환합니다." |

---

## 13. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-04-29 | 초안. 도구 7종 schema + 에러 코드 사전 + 사용 시나리오 |
