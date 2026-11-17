그룹 요약문만을 근거로 카드의 모든 필드를 각각 검증하세요.

- 의미를 유지한 요약과 의역은 SUPPORTED입니다.
- 수치, 대상, 조건, 시점, 한정 표현, 확정성이 달라지면 POSSIBLE_DISTORTION입니다.
- 요약문으로 뒷받침할 수 없으면 INSUFFICIENT_EVIDENCE입니다.
- 사실 주장이 없는 표현은 NON_ASSERTIVE입니다.
- 판단하기 어려우면 UNCERTAIN입니다.

입력된 unit_id를 유지하고, evidence는 그룹 요약문에서 직접 인용하세요.
각 결과에 unit_id, status, evidence, reason, error_type, suggested_text를 포함하세요.
