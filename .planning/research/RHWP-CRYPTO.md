# HWP 암호화 분석 (rhwp 기반)

## 1. rhwp 암호화 지원 여부

**중요 결론**: rhwp의 `crypto.rs`는 **사용자 비밀번호 기반 복호화를 전혀 지원하지 않는다**. 오직 **"배포용 문서(distribution document) = ViewText 스트림"** 한 가지 케이스만 처리한다.

- 처리 대상: FileHeader 플래그에서 `distribution` 비트(`flags & 0x04`)가 켜진 문서.
- **비밀번호로 암호화된 일반 문서**(`encrypted` 비트 `flags & 0x02`)는 코드에서 **즉시 거부**한다:
  - `mod.rs:137, 237` — `if file_header.flags.encrypted { return Err(ParseError::EncryptedDocument); }`
  - 에러 메시지: `"암호화된 문서는 지원하지 않습니다"`
- 공개키 암호화(`public_key_encrypted`, `0x100`)도 미지원.
- DRM 비트(`flags & 0x10`)에 대한 별도 처리도 없음.

따라서 **사용자가 비밀번호로 잠근 HWP 문서를 비밀번호로 푸는 코드는 rhwp에 존재하지 않는다.** 사용자가 원하는 "사용자 비밀번호 → 키 → AES 복호화" 파이프라인은 rhwp 안에서 찾을 수 없다.

### crypto.rs가 실제로 하는 일 (ViewText 난독화 해제)

배포용 문서(viewer-only로 한컴이 발급한 ViewText 스트림)를 풀어내는 알고리즘. 사용된 프리미티브:
- **MSVC LCG**(seed 4바이트 → `seed*214013+2531011`, 상위 비트 7FFF)
- **LCG 키스트림 + XOR**로 256바이트 헤더 복호화
- 헤더 안에 박힌 16바이트 키로 **AES-128 ECB**(자체 구현 — S-Box, Rcon, key expansion, inv_shift_rows/inv_sub_bytes/inv_mix_columns 직접)
- 복호 후 zlib/deflate 압축 해제

알고리즘은 AES이지만 **키 파생(KDF)은 비밀번호로부터 이루어지지 않는다.** 키는 파일 자체의 첫 256바이트 안에 (LCG XOR로) 난독화돼 들어 있을 뿐.

**우리 MCP에 포팅 금지**: 이 로직은 한컴이 배포용으로 발행한 뷰어 전용 문서의 보호 해제이며, 한국 저작권법 제104조의2(기술적 보호조치 무력화 금지) 충돌 소지 있음. 우리가 만드는 MCP는 사용자 본인이 비밀번호를 알고 있는 일반 암호 문서만 다룬다.

## 2. FileHeader 플래그 비트 (header.rs:74-91)

| 비트 | 의미 | rhwp 처리 | 우리 MCP 처리 (예정) |
|---|---|---|---|
| `0x01` compressed | zlib 압축 | 지원 | 지원 |
| **`0x02` encrypted** | **비밀번호 암호화** | **거부 (`EncryptedDocument`)** | **사용자 비번 받아 처리 (별도 구현)** |
| `0x04` distribution | 배포용 (ViewText) | 지원 (LCG+AES) | **명시적 거부** |
| `0x10` drm | DRM | 처리 없음 | **명시적 거부** |
| `0x80` digital_signature | 전자서명 | 처리 없음 | 검증 없이 패스 |
| `0x100` public_key_encrypted | 공개키 암호화 | 미지원 | 거부 |

## 3. ViewText 복호화 의사코드 (참고용 — MCP에 구현 안 함)

> 이 의사코드는 사용자 비밀번호와 **무관**. 우리 MCP에는 구현하지 않는다. 알고리즘 이해 목적으로만 보관.

```python
import zlib
from Crypto.Cipher import AES

def _next(state):
    state[0] = (state[0] * 214013 + 2531011) & 0xFFFFFFFF
    return (state[0] >> 16) & 0x7FFF

def decrypt_distribute_header(buf256: bytes) -> bytes:
    out = bytearray(buf256)
    state = [int.from_bytes(out[:4], "little")]
    n, key = 0, 0
    for i in range(256):
        if n == 0:
            key = _next(state) & 0xFF
            n   = (_next(state) & 0xF) + 1
        if i >= 4:
            out[i] ^= key
        n -= 1
    return bytes(out)
```

## 4. 사용자 비밀번호 복호화 — 우리가 직접 찾아야 함

rhwp에는 없는 영역. 한컴 공식 스펙상 일반적인 비밀번호 문서 복호화 흐름:
- **HWP 5.x**: 비밀번호 → SHA-1 해시(라운드 다회) → AES-128 또는 SEED 키 → 본문 복호화
- **HWP 3.x**: 별도 단순 알고리즘 (rhwp 처리 없음)

**Python 후보**:
- `pyhwp` (GPL): 비밀번호 문서 처리 일부 지원 가능성. 라이선스 충돌 주의 (GPL → 우리도 GPL이거나 호출 격리 필요)
- 직접 구현: `cryptography` 또는 `pycryptodome` + 한컴 공식 스펙 문서

→ **PYTHON-OSS 분석 결과 받은 후 결정**.

## 5. Python 등가 라이브러리 (참고)

- AES-128 ECB / CFB: `pycryptodome` 또는 `cryptography`
- zlib raw deflate: `zlib.decompress(data, -15)` (wbits=-15)
- OLE 컨테이너: `olefile`
- KDF (SHA-1 round): `hashlib`

## 6. 합법성 결정 사항 (우리 MCP)

| 케이스 | 정책 |
|---|---|
| `encrypted` (비번 잠금) | 사용자가 호출 시 password 인자로 입력 → 복호화 시도. 실패 시 명확한 에러. |
| `distribution` (ViewText) | **명시적 거부** + "DRM 보호 문서는 미지원" 메시지 |
| `drm` 비트 | **명시적 거부** + 동일 메시지 |
| `public_key_encrypted` | 거부 |
| `digital_signature` | 무시하고 진행 (서명 검증은 안 함) |

## 7. 관련 파일

- `_external/rhwp/src/parser/crypto.rs` (전체 분석 대상)
- `_external/rhwp/src/parser/header.rs` (line 45-91: 플래그 비트 정의)
- `_external/rhwp/src/parser/mod.rs` (line 137, 200-209, 237, 254-263: encrypted 거부 + ViewText 호출 흐름)
- `_external/rhwp/src/parser/tags.rs` (HWPTAG_DISTRIBUTE_DOC_DATA 상수)
