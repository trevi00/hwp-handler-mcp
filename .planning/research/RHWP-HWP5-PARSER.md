# HWP5 포맷 스펙 (rhwp 분석 기반)

소스: `_external/rhwp/src/parser/` 9개 파일 분석.

---

## 1. 컨테이너: OLE2 Compound File

HWP 5.0은 표준 OLE2/CFB(Compound File Binary) 컨테이너이다. 매직 바이트 `D0 CF 11 E0 A1 B1 1A E1` (mod.rs:54).

### 1.1 사용 스트림과 역할

`mod.rs:677-686`의 `collect_extra_streams`에서 알려진 스트림 경로 화이트리스트:

| 스트림 경로 | 역할 |
|-------------|------|
| `/FileHeader` | 256바이트 헤더 (시그니처, 버전, 플래그). 항상 비압축 |
| `/DocInfo` | 폰트/스타일/문단모양/글자모양/바인데이터 인덱스 등 참조 테이블. 압축 가능 |
| `/BodyText/Section{N}` | 본문 섹션 (N=0,1,...). 레코드 스트림. 압축 가능 |
| `/ViewText/Section{N}` | 배포용 문서의 본문 (암호화+압축). 별도 복호화 단계 필요 |
| `/BinData/BIN{XXXX}.{ext}` | 임베딩된 이미지/OLE 바이너리. ext는 jpg/png/OLE 등 |
| `/PrvImage` | 미리보기 썸네일 (PNG/BMP/GIF) |
| `/PrvText` | UTF-16LE 미리보기 텍스트 |
| `/Section{N}` | 구버전 호환 — 루트 레벨 섹션 (`cfb_reader.rs:125`) |

### 1.2 압축 처리

`cfb_reader.rs:550-568` `decompress_stream`: **raw deflate (wbits=-15) 우선 시도, 실패하면 표준 zlib 폴백**.

Python:
```python
import zlib
try:
    return zlib.decompress(raw, wbits=-15)   # raw deflate
except zlib.error:
    return zlib.decompress(raw)              # 표준 zlib
```

---

## 2. FileHeader 구조

`header.rs:1-159`. 256바이트 고정 비압축.

| 오프셋 | 크기 | 필드 | 비고 |
|--------|------|------|------|
| 0~31 | 32B | 시그니처 | `"HWP Document File"` (17B) + NULL 패딩 |
| 32 | u8 | revision | LE |
| 33 | u8 | build | |
| 34 | u8 | minor | |
| 35 | u8 | major | 5만 지원 |
| 36~39 | u32 LE | flags | 비트 플래그 |
| 40~43 | 4B | 라이선스 (예약) |
| 44~255 | 212B | 예약 | |

### 2.1 Flags 비트 (header.rs:74-92)

| 비트 마스크 | 의미 |
|-------------|------|
| `0x001` | compressed (DocInfo/BodyText DEFLATE) |
| `0x002` | encrypted |
| `0x004` | distribution (배포용 — ViewText 사용) |
| `0x008` | script |
| `0x010` | drm |
| `0x020` | xml_template |
| `0x040` | document_history |
| `0x080` | digital_signature |
| `0x100` | public_key_encrypted |
| `0x200` | modified_certificate |
| `0x400` | prepare_distribution |

지원 버전 체크: `major == 5 && minor in {0, 1}` (header.rs:30-32).

---

## 3. DocInfo 스트림

`doc_info.rs:1-826`. 압축 해제된 레코드 스트림.

### 3.1 등장 레코드 순서

```
DOCUMENT_PROPERTIES → ID_MAPPINGS → BIN_DATA → FACE_NAME →
BORDER_FILL → CHAR_SHAPE → TAB_DEF → PARA_SHAPE → STYLE
```

### 3.2 핵심 레코드 (텍스트 추출에는 대부분 불필요, 메타데이터에만)

#### HWPTAG_DOCUMENT_PROPERTIES (0x010)
- u16 section_count
- u16 page_start_num, footnote_start_num, endnote_start_num
- u16 picture_start_num, table_start_num, equation_start_num

#### HWPTAG_ID_MAPPINGS (0x011)
연속된 u32 카운트 16개: bin_data_count, font_counts[7](한/영/한자/일/기타/기호/사용자), border_fill_count, char_shape_count, tab_def_count, numbering_count, bullet_count, para_shape_count, style_count, memo_shape_count.

#### HWPTAG_BIN_DATA (0x012)
- u16 attr — bit 0~3=type (0=Link, 1=Embedding, 2=Storage), 4~5=compression, 8~9=status
- Embedding/Storage: u16 storage_id, hwp_string extension
- 파일명 규칙: `BIN{storage_id:04X}.{ext}`

---

## 4. BodyText/Section{N} 스트림

### 4.1 트리 구조

```
PARA_HEADER (level 0)
  PARA_TEXT (level 1)
  PARA_CHAR_SHAPE (level 1)
  PARA_LINE_SEG (level 1)
  CTRL_HEADER (level 1)         ← 'secd', 'cold', 'tbl ' 등
    PAGE_DEF (level 2)
    ...
```

### 4.2 PARA_HEADER 페이로드 (body_text.rs:213-247)

- u32 nChars: bit31=플래그, bit0~30=문자 수
- u32 controlMask
- u16 paraShapeId
- u8 styleId
- u8 breakType: `0x01`=구역 / `0x02`=다단 / `0x04`=쪽 / `0x08`=단 나누기

### 4.3 PARA_TEXT 인코딩 + 인라인 컨트롤 (body_text.rs:254-377) — **핵심**

UTF-16LE 스트림에서 `0x0000~0x001F` 범위는 컨트롤 문자. 종류에 따라 차지 크기가 다름:

| 종류 | 코드 | 크기 |
|------|------|------|
| char (1 code unit = 2바이트) | 0, 10, 13, 24-31 | 단순 문자 치환 |
| inline (8 code unit = 16바이트) | 4-9, 19-20 | CTRL_HEADER 없음 |
| extended (8 code unit = 16바이트) | 1-3, 11-12, 14-18, 21-23 | CTRL_HEADER와 1:1 대응 |

#### 특수 문자 매핑

| 코드 | 의미 | 표현 |
|------|------|------|
| 0x0000 | NULL | (스킵) |
| 0x0009 | TAB | `\t` (16바이트) |
| 0x000A | line break | `\n` (2바이트) |
| 0x000D | 문단 끝 | (스트림 종료) |
| 0x0018 | 묶음 빈칸 | ` ` |
| 0x0019 | 고정폭 빈칸 | `' '` |
| 0x001E | 하이픈 | `-` |
| 0x001F | FIGURE SPACE | ` ` |

서로게이트 페어(0xD800~0xDBFF + 0xDC00~0xDFFF) 정상 처리 필요.

### 4.4 CTRL_HEADER 디스패치

CTRL_HEADER 데이터 첫 4바이트 = u32 ctrl_id (big-endian 인코딩된 ASCII; 디스크에는 LE로 저장).

`secd` 구역, `cold` 단, `tbl ` 표, `eqed` 수식, `gso ` 그림, `head/foot` 머리/꼬리, `fn  /en  ` 각/미주, `pgnp/pghd` 쪽번호, `idxm/bokm` 색인/책갈피.

---

## 5. 레코드 헤더 인코딩 (record.rs)

```
┌───────────┬───────────┬─────────────────┐
│ size:12   │ level:10  │ tag_id:10       │
│ bits 20-31│ bits 10-19│ bits 0-9        │
└───────────┴───────────┴─────────────────┘
```

```python
header = struct.unpack_from('<I', data, pos)[0]
tag_id = header & 0x3FF
level  = (header >> 10) & 0x3FF
size   = (header >> 20) & 0xFFF
pos += 4
if size == 0xFFF:
    size = struct.unpack_from('<I', data, pos)[0]   # 확장 size
    pos += 4
```

`read_hwp_string`: u16 글자수 + UTF-16LE 바이트.

---

## 6. tags.rs 매핑 (HWPTAG_BEGIN = 0x010)

### DocInfo 태그

| 태그 ID | 상수 |
|---------|------|
| 0x10 | DOCUMENT_PROPERTIES |
| 0x11 | ID_MAPPINGS |
| 0x12 | BIN_DATA |
| 0x13 | FACE_NAME |
| 0x14 | BORDER_FILL |
| 0x15 | CHAR_SHAPE |
| 0x19 | PARA_SHAPE |
| 0x1A | STYLE |
| 0x1C | DISTRIBUTE_DOC_DATA |

### BodyText 태그 (오프셋 50~)

| 태그 ID | 상수 |
|---------|------|
| **0x42 (66)** | **PARA_HEADER** |
| **0x43 (67)** | **PARA_TEXT** |
| 0x44 | PARA_CHAR_SHAPE |
| 0x45 | PARA_LINE_SEG |
| 0x47 | CTRL_HEADER |
| 0x48 | LIST_HEADER |
| 0x4D | TABLE |
| 0x55 | SHAPE_COMPONENT_PICTURE |

---

## 7. 텍스트 추출 최소 경로 (Python 의사코드)

```python
import io, zlib, struct, olefile

def extract_text(hwp_bytes):
    ole = olefile.OleFileIO(io.BytesIO(hwp_bytes))

    hdr = ole.openstream('FileHeader').read()
    assert hdr[:17] == b'HWP Document File'
    flags = struct.unpack_from('<I', hdr, 36)[0]
    compressed   = bool(flags & 0x01)
    encrypted    = bool(flags & 0x02)
    distribution = bool(flags & 0x04)
    if encrypted:
        raise NotImplementedError("암호화 문서 — 비밀번호 필요 (별도 경로)")
    if distribution:
        raise NotImplementedError("배포용(ViewText) DRM 보호 문서 미지원")

    sections = []
    i = 0
    while True:
        path = f'BodyText/Section{i}'
        if not ole.exists(path):
            break
        raw = ole.openstream(path).read()
        if compressed:
            raw = zlib.decompress(raw, wbits=-15)
        sections.append(raw)
        i += 1

    text_parts = []
    for section_bytes in sections:
        for tag_id, level, body in read_all_records(section_bytes):
            if tag_id == 67:  # PARA_TEXT
                text_parts.append(decode_para_text(body))
    return '\n'.join(text_parts)


def read_all_records(data):
    pos = 0
    while pos + 4 <= len(data):
        header = struct.unpack_from('<I', data, pos)[0]
        tag_id = header & 0x3FF
        level  = (header >> 10) & 0x3FF
        size   = (header >> 20) & 0xFFF
        pos += 4
        if size == 0xFFF:
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        yield tag_id, level, data[pos:pos+size]
        pos += size


def decode_para_text(data):
    """body_text.rs:254-377 Python 포팅."""
    out = []
    pos = 0
    BIG = (set(range(1, 10)) | {11, 12} | set(range(14, 24))) - {9, 10}
    SPECIAL_CHAR = {0x18: ' ', 0x19: ' ', 0x1E: '-', 0x1F: ' '}

    while pos + 1 < len(data):
        ch = struct.unpack_from('<H', data, pos)[0]
        if ch == 0x0000:
            pos += 2
        elif ch == 0x0009:                # TAB (16바이트)
            out.append('\t'); pos += 16
        elif ch == 0x000A:                # LF
            out.append('\n'); pos += 2
        elif ch == 0x000D:                # 문단 끝
            break
        elif ch in BIG:
            if ch == 0x0012:              # AutoNumber → ' '
                out.append(' ')
            pos += 16
        elif ch < 0x0020:
            if ch in SPECIAL_CHAR:
                out.append(SPECIAL_CHAR[ch])
            pos += 2
        else:
            if 0xD800 <= ch <= 0xDBFF and pos + 3 < len(data):
                low = struct.unpack_from('<H', data, pos+2)[0]
                if 0xDC00 <= low <= 0xDFFF:
                    cp = 0x10000 + ((ch - 0xD800) << 10) + (low - 0xDC00)
                    out.append(chr(cp))
                    pos += 4
                    continue
            out.append(chr(ch))
            pos += 2
    return ''.join(out)
```

---

## 8. 발견한 함정/특수 케이스

### 8.1 컨트롤 문자의 이중성
같은 0~31 범위인데 **inline/extended는 16바이트, char는 2바이트**. 잘못 분류하면 그 뒤 모든 텍스트가 깨짐.

### 8.2 FIELD_BEGIN/FIELD_END 비대칭
- 0x0003 FIELD_BEGIN: extended (16B), controls[]에 카운트됨
- 0x0004 FIELD_END: inline (16B), **controls[]에 카운트 안 됨**
- 중첩 가능 → 스택으로 추적

### 8.3 size==0xFFF 확장 헤더
4095바이트 이상 레코드는 헤더 4B + 추가 size 4B = 8B 헤더. 데이터 시작 오프셋 계산 실수 빈번.

### 8.4 BorderFill의 인터리브 형식
스펙 문서는 "타입 4개 → 굵기 4개 → 색 4개"처럼 보일 수 있지만 **실제는 `[type, width, color] × 4`**.

### 8.5 FootnoteShape 28바이트 vs 스펙 26바이트
스펙은 26B인데 실제 데이터는 28B. note_spacing과 separator_line_type 사이에 미문서화 2바이트.

### 8.6 PARA_TEXT의 0x000D는 문단 끝
이걸 만나면 break — PARA_TEXT는 한 문단 1개씩 나오므로 보통 끝까지 가지만 조기 종료 신호.

### 8.7 LIST_HEADER 오분류
파일 끝의 확장 바탕쪽 LIST_HEADER(level=1)가 마지막 PARA_HEADER의 자식으로 보임. 텍스트 추출만 한다면 무시 OK.

### 8.8 Section/페이지/단 분리
- Section: `BodyText/Section{N}`마다 별도 스트림
- 페이지/단: PARA_HEADER.breakType 비트 플래그만, 명시적 마커 없음

### 8.9 ctrl_id의 BE vs 디스크 LE
파일 바이트 `[d, c, b, a]` ↔ const u32로는 BE 인코딩(`'a'`이 MSB).

```python
ctrl_id = struct.unpack_from('<I', data, off)[0]
# 비교: ctrl_id == int.from_bytes(b'secd', 'big')
```

### 8.10 배포용 문서 (distribution flag)
ViewText 스트림은 raw가 암호화 + 압축. **우리 MCP는 명시적 거부** (RHWP-CRYPTO.md 참조).

---

## 9. Python 매핑 권고

### 9.1 충분한 도구 조합 (텍스트 추출 한정)

`olefile` + `zlib` + `struct`만으로 **모든 단계가 가능**. 의존성 최소화.

| 작업 | Python 라이브러리 |
|------|-------------------|
| CFB 컨테이너 열기 | `olefile` |
| DEFLATE 해제 | `zlib.decompress(data, wbits=-15)` |
| LE 정수/UTF-16LE | `struct` + `bytes.decode('utf-16-le')` |

### 9.2 pyhwp가 이미 처리하는 것

`pyhwp` (Python 패키지)는 다음을 이미 제공:
- FileHeader 파싱 (시그니처, 버전, flags)
- Record 트리 (HWPTAG_*, level, 확장 size 0xFFF)
- DocInfo 레코드 디코딩 (FACE_NAME, CHAR_SHAPE, PARA_SHAPE, STYLE, BORDER_FILL)
- BodyText 단락/컨트롤 분해
- `hwp5proc`/`hwp5txt` CLI는 텍스트 추출 즉시 가능

→ **MCP 서버에서는 pyhwp의 hwp5txt를 활용하거나 내부 모델 import해서 paragraph 트리만 순회**가 빠름.

### 9.3 직접 구현 또는 참고가 필요한 것

- **HWPX 지원**: pyhwp는 HWP 5만. (HWPX 파서 분석 결과 별도)
- **인라인 컨트롤 placeholder**: pyhwp가 어떻게 표현하는지 확인. rhwp는 0x0012를 ' '로 두고 후처리.
- **OLE Storage 내부 추출**: 이미지/차트 추출 시 필요. 텍스트엔 불필요.

### 9.4 Rust → Python 어댑테이션

| Rust | Python |
|------|--------|
| `&[u8]`, `Cursor<&[u8]>` | `memoryview(bytes)` 또는 `bytes` + offset |
| `Read` + `byteorder` | `struct.unpack_from('<...', buf, off)` |
| `String::from_utf16_lossy` | `bytes.decode('utf-16-le', errors='replace')` |
| `cfb::CompoundFile` | `olefile.OleFileIO` |
| flate2 `DeflateDecoder` | `zlib.decompress(raw, wbits=-15)` |

### 9.5 권장 구현 순서 (MCP 텍스트 추출)

1. olefile로 컨테이너 + FileHeader flags
2. BodyText/Section{N} enumerate + zlib 해제
3. Record 평면 파서 (size==0xFFF 처리)
4. PARA_TEXT만 골라 decode_para_text
5. 결과 '\n' join

이 단계까지면 한국어 텍스트는 99% 추출. 이미지/표/필드값 필요하면 그때 CTRL_HEADER 처리 추가.

**rhwp 정오표 활용**: 인터리브 BorderFill, FootnoteShape 28바이트, 미문서화 비트 시프트 등 rhwp가 발견한 정오표는 그대로 차용.

---

**참고 파일**: `_external/rhwp/src/parser/{mod,cfb_reader,ole_container,header,doc_info,body_text,record,tags,byte_reader}.rs`
