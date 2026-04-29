# HWPX 포맷 스펙 (rhwp 분석 기반)

소스: `_external/rhwp/src/parser/hwpx/{mod,reader,header,content,section,utils}.rs`, 보조 `_external/rhwp/mydocs/eng/feedback/hwpx2ir.md`.

표준 표기는 rhwp 코드의 doc-comment 인용. 코드에 직접 보이지 않는 항목은 *코드에 없음*으로 명시.

---

## 1. ZIP 컨테이너 구조

HWPX는 **ZIP 아카이브** + ePub과 유사한 OPF(Open Packaging Format) 차용. 표준명: KS X 6101:2024.

### rhwp가 실제로 읽는 엔트리

| 경로 | 역할 |
|------|------|
| `Contents/content.hpf` | 패키지 매니페스트 + spine |
| `Contents/header.xml` | 글꼴/글자모양/문단모양/스타일/테두리 등 리소스 테이블 |
| `Contents/section{N}.xml` | 본문 섹션 (N=0..). spine 순서로 순회 |
| `BinData/<file>` | 임베드 이미지 등 |
| `Chart/chart{N}.xml` (N=1..64) | OOXML 차트. break-on-miss 루프 |

### 코드에 *없는* 엔트리 (rhwp는 읽지 않음 — Python 구현 시 별도 조사 필요)

- **`mimetype`** 최상위 엔트리 (관례상 `application/hwp+zip`)
- **`META-INF/container.xml`** (rhwp는 `Contents/content.hpf` 위치를 하드코딩)
- **`version.xml`** (rhwp는 항상 `5.1.0.0`로 채움)
- **`Preview/PrvText.txt`**, **`settings.xml`**, **`Scripts/`**
- **메타데이터 properties XML** (작성자/제목/생성일 등)

### 압축 폭탄 방어 (Python 구현 시 답습)

- `MAX_XML_SIZE = 32 MB` (XML 엔트리당)
- `MAX_BINDATA_SIZE = 64 MB` (바이너리 엔트리당)
- `Read::take(max+1)`로 1바이트만 더 읽어 초과 시 `InvalidData` 에러

---

## 2. XML 네임스페이스 매핑

rhwp는 **네임스페이스 처리를 우회**한다. 모든 곳에서 단순 prefix-strip:

```rust
pub fn local_name(name: &[u8]) -> &[u8] {
    if let Some(pos) = name.iter().position(|&b| b == b':') {
        &name[pos + 1..]
    } else { name }
}
```

코드에 등장하는 prefix:
- `hp:` — 본문/문단 (`hp:p`, `hp:run`, `hp:t`, `hp:tbl`, `hp:pic`, `hp:secPr`, `hp:tab`, `hp:lineBreak`, `hp:nbSpace`, `hp:fwSpace`, `hp:ctrl`, `hp:switch`, `hp:chart`, `hp:ole`, `hp:equation`)
- `hh:` — 헤더 리소스 (`hh:fontface`, `hh:font`, `hh:charPr`, `hh:paraPr`, `hh:strikeout`, `hh:color`, `hh:borderFill`)
- `hs:` — 섹션 정의(추정)
- `opf:` — content.hpf (`opf:manifest`, `opf:item`, `opf:spine`, `opf:itemref`)

**Python 매핑**: lxml에서 `etree.QName(elem).localname` 또는 `tag.split('}')[-1]`로 prefix 무시. 표준 준수가 필요하면 ns map 명시 등록.

---

## 3. `Contents/content.hpf` (OPF 매니페스트)

```xml
<opf:package>
  <opf:manifest>
    <opf:item id="..." href="..." media-type="..."/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="..." linear="yes"/>
  </opf:spine>
</opf:package>
```

### rhwp 추출 규칙

1. 모든 `<opf:item>`을 `(id, href, media-type)`로 수집
2. 모든 `<opf:itemref idref="...">`로 spine 순서 모음
3. **섹션**: spine 순서대로 순회 — `media-type == "application/xml"` AND `href.contains("section")`만 추출. spine 비어있으면 매니페스트에서 fallback + href 알파벳 정렬
4. **BinData**: `href`가 `BinData/`로 시작하거나 `/BinData/` 포함

---

## 4. `header.xml` 핵심 요소

문서 전체에서 ID로 참조되는 **리소스 테이블**.

### rhwp가 파싱하는 최상위 자식

| 태그 (local) | 쓰임 |
|--------------|------|
| `<hh:beginNum page footnote endnote pic tbl equation>` | 시작 번호 → DocProperties |
| `<hh:fontface lang="HANGUL\|LATIN\|HANJA\|JAPANESE\|OTHER\|SYMBOL\|USER">` | 언어별 글꼴 그룹 |
| `<hh:font face="...">` | 글꼴 |
| `<hh:charPr height textColor shadeColor borderFillIDRef>` | 글자모양 |
| `<hh:paraPr tabPrIDRef>` | 문단모양 |
| `<hh:style name engName type paraPrIDRef charPrIDRef nextStyleIDRef>` | 스타일 |
| `<hh:borderFill>` | 테두리/채우기 |
| `<hh:tabPr autoTabLeft autoTabRight>` | 탭 정의 |
| `<hh:numbering start>` | 번호 매기기 |

### 메타데이터 (작성자/생성일/제목)

**rhwp는 이를 추출하지 않는다.** `mod.rs:134-141`은 FileHeader에 하드코딩 `5.1.0.0`을 채우고 끝.

→ Python 구현은 OWPML/OPC 표준 또는 `Contents/content.hpf`의 `<opf:metadata>`를 별도 조사 필요.

### 색상 표기 (utils.rs:61)

`#RRGGBB` / `#AARRGGBB`(alpha 무시) / `none`(0xFFFFFFFF). HWP 내부 표현 `0x00BBGGRR`로 변환.

### `<switch>/<case required-namespace="...HwpUnitChar">/<default>` 분기

HWPX는 일부 단위(margin, lineSpacing, tabItem.pos)를 두 단위로 표기:
- `case` (HwpUnitChar) → HWPUNIT (1× 스케일). HWP 바이너리와 동일 단위 변환 시 ×2
- `default` → 이미 HWP 바이너리 단위 (2× 스케일)
- 우선순위: case 발견 시 case, 없으면 default

---

## 5. `section{N}.xml` 트리 구조

### 최상위 흐름

```
section root
└── <hp:p paraPrIDRef styleIDRef columnBreak pageBreak>
    ├── <hp:run charPrIDRef>
    │   └── <hp:t> ... 텍스트 ... </hp:t>
    ├── <hp:tbl rowCnt colCnt borderFillIDRef>
    ├── <hp:pic>
    ├── <hp:rect|ellipse|line|arc|polygon|curve|container>
    ├── <hp:secPr>          ← 첫 문단에 동봉되는 섹션 정의
    ├── <hp:linesegarray>   ← <hp:lineseg> 줄 좌표 배열
    ├── <hp:ctrl>           ← header/footer/footnote/endnote/autoNum
    ├── <hp:switch> / <hp:chart> / <hp:ole>
    ├── <hp:compose>        ← 글자겹침
    ├── <hp:dutmal>         ← 덧말(루비)
    ├── <hp:equation>
    └── <hp:btn|checkBtn|radioBtn|comboBox|edit>
```

### 텍스트 노드 (`<hp:t>`) — 핵심

`<hp:t>` 안에서 발생하는 이벤트:

- **`Event::Text`** → `t.decode()`로 그대로 push
- **`<hp:lineBreak/>`** → `\n`
- **`<hp:columnBreak/>`** → `\n`
- **`<hp:tab width leader type>`** → `\t` + 인라인 탭 메타
- **`<hp:nbSpace/>`** → U+00A0 (NBSP)
- **`<hp:fwSpace/>`** → U+2007 (FIGURE SPACE)

### 표 (`<hp:tbl>`)

- 속성: `rowCnt`, `colCnt`, `cellSpacing`, `borderFillIDRef`
- 자식: `<hp:tr>` (행), `<hp:tc>` (셀), `<hp:caption>`
- 셀 내부: `<hp:cellAddr>`, `<hp:cellSpan>`, `<hp:cellSz>`, `<hp:cellMargin>`, `<hp:subList>` (재귀 `<hp:p>` 트리)

### 이미지 (`<hp:pic>`)

- `<hp:img binaryItemIDRef="image1">` — `binaryItemIDRef`가 BinData 연결 키
- rhwp는 문자열에서 ASCII 숫자만 추출 (`"image1"` → `1`)

### `<hp:ctrl>` 자식 (제어 객체)

- `<hp:colPr>` — 단 정의
- `<hp:header>` / `<hp:footer>`
- `<hp:footNote>` / `<hp:endNote>`
- `<hp:autoNum>` — 텍스트에 placeholder space 1개
- `<hp:fieldBegin>` / `<hp:fieldEnd>` — 텍스트에 U+0003/U+0004 삽입
- `<hp:bookmark>`, `<hp:pageNum>`, `<hp:hiddenComment>`

### `<hp:secPr>` — 섹션 정의

자식: `<hp:pagePr width height landscape>`, `<hp:margin>`, `<hp:colPr>`, `<hp:startNum>`, `<hp:visibility>`. landscape 무시 (HWPX는 width/height가 이미 회전된 상태).

---

## 6. 텍스트 추출 최소 경로 (Python 의사코드)

```python
import io, zipfile
from lxml import etree

NS_STRIP = lambda tag: tag.split('}')[-1] if '}' in tag else tag.split(':')[-1]

def extract_text(hwpx_bytes: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(hwpx_bytes))

    # 1. content.hpf → spine 순서 섹션 목록
    hpf_root = etree.fromstring(z.read("Contents/content.hpf"))
    items = {it.get("id"): it.get("href")
             for it in hpf_root.iter() if NS_STRIP(it.tag) == "item"}
    spine = [it.get("idref") for it in hpf_root.iter() if NS_STRIP(it.tag) == "itemref"]

    section_paths = []
    for idref in spine:
        href = items.get(idref, "")
        if "section" in href and href.endswith(".xml"):
            section_paths.append(href)

    # fallback: spine이 비었을 때
    if not section_paths:
        section_paths = sorted(h for h in items.values()
                               if "section" in h and h.endswith(".xml"))

    # 2. 각 섹션의 텍스트만 모음
    chunks = []
    for path in section_paths:
        root = etree.fromstring(z.read(path))
        for elem in root.iter():
            if NS_STRIP(elem.tag) == "p":
                for sub in elem.iter():
                    name = NS_STRIP(sub.tag)
                    if name == "t" and sub.text:
                        chunks.append(sub.text)
                    elif name in ("lineBreak", "columnBreak"):
                        chunks.append("\n")
                    elif name == "tab":
                        chunks.append("\t")
                    elif name == "nbSpace":
                        chunks.append(" ")
                    elif name == "fwSpace":
                        chunks.append(" ")
                chunks.append("\n")  # 단락 경계
    return "".join(chunks)
```

(rhwp는 추가로 표 안 셀 텍스트도 `<hp:p>` 재귀로 자연 추출. 위 코드도 `root.iter()`로 동일 동작.)

---

## 7. 메타데이터 추출 위치

| 항목 | rhwp가 읽는가? | 위치 |
|------|---------------|------|
| HWPX 버전 | **아니오** (5.1.0.0 하드코딩) | (코드에 없음) |
| 섹션 수 | 예 | content.hpf spine |
| 페이지/각주/표/그림 시작 번호 | 예 | header.xml `<hh:beginNum>` |
| 단/단방향/단 너비 | 예 | section.xml `<hp:secPr>/<hp:colPr>` |
| 페이지 크기/여백 | 예 | `<hp:secPr>/<hp:pagePr>` `<hp:margin>` |
| **작성자/제목/생성일/수정일** | **rhwp 미읽음** | Python 구현 시 OPC 표준/별도 metadata XML 조사 필요 |

---

## 8. Gotchas

1. **빈 단락**: `text_parts`가 비어도 Paragraph는 항상 생성. 빈 단락 = 빈 줄 1개.
2. **단락 vs 줄바꿈**:
   - `<hp:p>` 경계 = 진짜 단락 (`\n` 추가 권장)
   - `<hp:lineBreak/>` / `<hp:columnBreak/>` = 단락 내부 강제 줄바꿈
3. **제어 문자 마커**:
   - `\u{0002}` = 인라인 객체 자리 (표/이미지/도형/수식/차트/OLE/폼). UTF-16 폭 8
   - `\u{0003}` = 필드 시작 (`<hp:fieldBegin>`). 폭 8
   - `\u{0004}` = 필드 끝 (`<hp:fieldEnd>`). 폭 8
   - 시각 텍스트 추출 시 무시
4. **공백 문자**: nbSpace → U+00A0, fwSpace → U+2007
5. **탭 너비**: `<hp:tab/>`는 `\t` 1글자지만 UTF-16 길이 계산 시 8로 침
6. **strikeout 화이트리스트**: `shape="3D"`는 placeholder, 진짜 취소선 아님. OWPML LineSym2 13종만 인정
7. **HwpUnitChar switch/case**: case 값은 ×2 스케일링
8. **landscape 무시**: HWPX의 `<hp:pagePr landscape="1">`은 width/height 이미 회전됨
9. **이미지 ID 추출**: `binaryItemIDRef="image1"` → ASCII 숫자만 뽑아 ID로 사용
10. **차트**: `Chart/chart{N}.xml`을 N=1..64 break-on-miss 스캔 (매니페스트 무시)
11. **LINE_SEG 비어있음**: HWPX 본문 문단의 `<hp:linesegarray>`는 자주 비어있음. 텍스트 추출엔 무관, 렌더링/페이지네이션엔 직접 계산 필요
12. **네임스페이스 검증 부재**: rhwp는 `xmlns` URI를 검증하지 않음. malformed 파일에 robust하지만 표준 준수 검증은 별도 필요

---

## 9. Python 매핑 권고

### 라이브러리 선택

- **`zipfile` (stdlib)**로 충분. 압축 폭탄 방어를 위해 엔트리별 길이 체크 (rhwp의 `MAX_XML_SIZE=32MB`, `MAX_BINDATA_SIZE=64MB` 답습)
- **`lxml.etree`** — 한국어 인코딩, 네임스페이스, XPath 모두 풍부

### `iterparse` vs `fromstring`

- `content.hpf`, `header.xml`: `etree.fromstring()` 통째 처리 OK
- `section{N}.xml`: 32MB 이내면 `fromstring`. 대형 문서는 `iterparse(events=("start","end"))` + `clear()` 권장
- 텍스트만 뽑는 단순 케이스: `fromstring` + `.iter()`가 가독성 압도

### 함수 시그니처 권고

```python
def parse_hwpx(data: bytes) -> dict:
    """
    반환: {
      "sections": [{"text": str, "paragraphs": [...]}],
      "bin_data": [(bin_id, ext, bytes)],
      "version": (5,1,0,0),
      "section_count": int,
    }
    """
```

---

## 부록: `<hp:p>` 직속 자식 빠른 참조

| 로컬 태그 | 텍스트 영향 | rhwp 처리 |
|-----------|-----------|-----------|
| `run` | charPrIDRef 변경점 | `current_char_shape_id` 업데이트 |
| `t` | 실제 텍스트 source | `read_text_content_with_tabs` |
| `tbl` | `\u{0002}` 1개 + 표 자체 컨트롤 | `parse_table` 재귀 |
| `pic`, `rect`, `ellipse`, `line`, `arc`, `polygon`, `curve`, `container`, `compose`, `dutmal`, `equation`, `btn`, `checkBtn`, `radioBtn`, `comboBox`, `edit` | `\u{0002}` 1개 | 각각 전용 parser |
| `switch` | `\u{0002}` 1개 | `parse_switch_chart_or_ole` |
| `chart`, `ole` | `\u{0002}` 1개 | `parse_hp_chart_element`, `parse_hp_ole_element` |
| `secPr` | 무영향 | 섹션 정의 채움 |
| `linesegarray` | 무영향 | LineSeg 배열 채움 |
| `lineBreak`, `columnBreak`, `softHyphen` | `\n` | text_parts.push |
| `tab` | `\t` | text_parts.push |
| `lineseg` (단독) | 무영향 | LineSeg 1개 push |
| `ctrl` | autoNum=" ", fieldBegin="\u{0003}", fieldEnd="\u{0004}" | `parse_ctrl` 분기 |
