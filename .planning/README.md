# hwp-mcp Planning

파이프라인 기반 진행. 각 단계 산출물은 다음 단계 입력.

## 단계
1. **requirements/** — REQUIREMENTS.md (MCP tool surface, 입출력 계약, 에러 케이스)
2. **conventions/** — CODE-STYLE.md (Python/MCP 컨벤션)
3. **design/** — FORMAT-IR.md (HWP→IR 매핑), MCP-API.md (tool schema)
4. **research/** — RHWP-PARSER.md, PYTHON-OSS.md, HWP-SPEC.md (병렬 분석 결과)
5. (스캐폴딩/구현/검증은 src/, tests/에 직접)

## DGE 원칙
- 각 단계는 **Designer → Generator → Evaluator** 사이클
- 다음 단계로 가기 전 검증 통과 필수
- 같은 유형 문제 2회 → 컨벤션 또는 훅 규칙으로 영구 코드화
