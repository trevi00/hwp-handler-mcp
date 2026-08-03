# 실제 HWP 5.x 샘플 출처

이 디렉터리의 `.hwp` 파일은 [neolord0/hwplib](https://github.com/neolord0/hwplib) 의 `sample_hwp/basic/` 에서 가져왔습니다.

- 라이선스: Apache License 2.0 (본 프로젝트와 동일)
- 용도: 실제 한컴 오피스가 생성한 파일에 대한 회귀 테스트

| 파일 | 원본 경로 |
|---|---|
| `blank.hwp` | `sample_hwp/basic/blank.hwp` |
| `footnote_endnote.hwp` | `sample_hwp/basic/각주미주.hwp` |
| `header_footer.hwp` | `sample_hwp/basic/머리글꼬리글.hwp` |
| `textbox.hwp` | `sample_hwp/basic/글상자.hwp` |

합성 픽스처만으로는 실제 문서에서만 드러나는 파싱 결함을 잡지 못한다는 것이
실측으로 확인되어(HWPX 표 추출이 조용히 0개를 반환) 실물 코퍼스를 동봉한다.
