<!-- mcp-name: io.github.trevi00/hwp-handler-mcp -->

# hwp-handler-mcp

[![PyPI](https://img.shields.io/pypi/v/hwp-handler-mcp)](https://pypi.org/project/hwp-handler-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/hwp-handler-mcp)](https://pypi.org/project/hwp-handler-mcp/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

An MCP server for **Korean HWP / HWPX documents** — the format used by Hancom Office
(한글), the de-facto standard for Korean government and corporate paperwork.

Reads `.hwp` (HWP 5.x binary) and `.hwpx` (OWPML), and **edits or generates** `.hwpx`
— including filling form tables by label, which is what most Korean office work
actually needs.

한국어 안내는 [아래 섹션](#한국어)을 보세요.

---

## Quick start

```bash
# Run directly, no install
uvx hwp-handler-mcp

# Or install
pip install hwp-handler-mcp
```

### Claude Code

```bash
claude mcp add hwp -- uvx hwp-handler-mcp
```

### Claude Desktop / Cursor

Add to `claude_desktop_config.json` (or your client's MCP config):

```json
{
  "mcpServers": {
    "hwp": {
      "command": "uvx",
      "args": ["hwp-handler-mcp"],
      "env": { "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

`PYTHONIOENCODING` matters on Windows — Korean text in log output can otherwise
raise encoding errors on `cp949` consoles.

---

## Tools

### Reading

| Tool | What it does |
|---|---|
| `extract_text` | Body text, with paging (`offset` / `max_chars`) |
| `convert_to_markdown` | Whole document as Markdown — feed a 한글 file straight to an LLM |
| `extract_tables` | Tables as row/column matrices |
| `extract_metadata` | Title, author, last author, created/modified timestamps |
| `detect_format` | Format, version, and security flags (encrypted / DRM / distribution-protected) |
| `list_attachments` | Embedded images and OLE objects |
| `read_attachment` | One attachment's bytes, base64-encoded |
| `inspect_structure` | Raw container dump (streams, sizes, SHA-256) for forensics |

### Writing (HWPX only)

| Tool | What it does |
|---|---|
| `fill_form` | Fill table cells **by label** — `{"성명 > right": "김철수"}` |
| `replace_text` | Bulk text replacement, reports per-pattern counts |
| `create_document` | New document from paragraphs and tables |
| `set_header_footer` | Set header / footer text |

`fill_form` is the one to reach for with Korean forms. Instead of blind string
replacement, it locates the cell holding a label and writes into the neighbouring
cell (`right` / `left` / `below` / `above`), then reports exactly which paths were
applied and which were not found:

```json
{
  "applied": [{"path": "성명 > right", "table_index": 0, "row": 0, "col": 1, "value": "김철수"}],
  "failed": [],
  "applied_count": 1,
  "failed_count": 0
}
```

---

## What works on which format

| | `.hwp` (HWP 5.x) | `.hwpx` |
|---|---|---|
| Extract text | ✅ | ✅ |
| Format / version / security flags | ✅ | ✅ |
| Metadata | ✅ when the document carries a summary stream | ✅ |
| Attachments (list / read) | ✅ | ✅ |
| Structure dump | ✅ | ✅ |
| Tables as structured data | ❌ returns a warning | ✅ |
| Markdown conversion | text only, warns about tables | ✅ tables included |
| Create / edit / fill | ❌ explicit error | ✅ |

### Known limitations

These are refusals with a clear error, not silent failures:

- **Encrypted documents are not supported.** Password-protected `.hwp` files are
  rejected with `PASSWORD_REQUIRED`. There is no password parameter — the feature
  does not exist yet, so the API does not pretend it does.
- **DRM-protected and 배포용(ViewText) documents are refused by policy**, as are
  public-key-encrypted files.
- **Writing `.hwp` is not supported.** No pure-Python HWP 5.x writer exists; the
  binary format would need Hancom's COM automation, which is Windows-only and
  requires 한글 to be installed. Save as `.hwpx` and every write tool works.
- **HWP 5.x table decomposition is not implemented.** Text inside tables still
  appears in `extract_text`; only the row/column structure is missing.
- **HWP 3.x (한글 97/98) is not supported.**

---

## How this is verified

The test suite runs against **real Hancom-produced `.hwp` files**, not only
hand-built fixtures. That distinction was not academic: an earlier version of the
table extractor called an API that does not exist, caught the failure, and returned
"0 tables" silently. Every synthetic test passed, because the synthetic fixtures
had no tables in them.

- Real `.hwp` corpus vendored from [neolord0/hwplib](https://github.com/neolord0/hwplib)
  (Apache-2.0, same as this project) — see `tests/fixtures/real_hwp5/ATTRIBUTION.md`
- HWPX round-trips are written by `python-hwpx` and read back by **our** parser, so
  producer and consumer are independent
- Write tools are verified by re-reading the saved file, not by trusting return values
- The suite runs against **both MCP SDK 1.x and 2.x**

```bash
uv sync --all-extras
uv run pytest          # 98 tests
uv run ruff check src tests
uv run mypy src
```

---

## Safety notes

- **Write tools never overwrite by accident.** An existing output path requires
  `overwrite=true`; omitting `output_path` requires `in_place=true`.
- **Untrusted XML is parsed defensively.** HWPX is a ZIP of XML, and extracted
  metadata flows into an LLM's context — an internal entity is a prompt-injection
  vector. Entity declarations are refused outright (`defusedxml`), and oversized
  `content.hpf` payloads are skipped rather than expanded.

---

## 한국어

한컴오피스 한글 문서(`.hwp` / `.hwpx`)를 다루는 MCP 서버입니다.

### 되는 것

- `.hwp`(HWP 5.x 바이너리)와 `.hwpx` **읽기** — 본문, 표, 메타데이터, 첨부, 구조 덤프
- `.hwpx` **편집·생성** — 문서 만들기, 텍스트 치환, 머리말/꼬리말
- **양식 채우기(`fill_form`)** — `{"성명 > right": "김철수"}` 처럼 표의 라벨을 찾아
  옆 칸에 값을 씁니다. 공문·신청서 작성이 주 용도이고, 못 찾은 라벨은 조용히
  넘어가지 않고 `failed` 로 돌려줍니다.
- **`convert_to_markdown`** — 한글 문서를 Markdown으로 바꿔 LLM에 그대로 물립니다.

### 안 되는 것 (명시적 오류로 알려줍니다)

- 암호가 걸린 문서 — 복호화는 구현되어 있지 않습니다. `password` 인자도 두지
  않았습니다. 없는 기능을 있는 것처럼 보이게 하지 않기 위해서입니다.
- DRM·배포용(ViewText)·공개키 암호화 문서 — 정책상 거부합니다.
- `.hwp` 쓰기 — 순수 Python 구현이 없습니다. `.hwpx`로 저장하면 모든 쓰기 도구가
  동작합니다.
- `.hwp`의 표 구조 분해 — 표 안 텍스트는 `extract_text`에 나오지만 행/열 구조는
  아직 없습니다.
- HWP 3.x(한글 97/98).

### 설치

```bash
claude mcp add hwp -- uvx hwp-handler-mcp
```

Windows에서는 `PYTHONIOENCODING=utf-8`을 함께 주는 것을 권장합니다. `cp949`
콘솔에서 한글 로그가 인코딩 오류를 낼 수 있습니다.

---

## Development

```bash
git clone https://github.com/trevi00/hwp-handler-mcp
cd hwp-handler-mcp
uv sync --all-extras
uv run pytest
```

Built on [python-hwpx](https://pypi.org/project/python-hwpx/) for OWPML handling.
The HWP 5.x reader is a native record parser (olefile + zlib + struct).

## License

Apache-2.0
