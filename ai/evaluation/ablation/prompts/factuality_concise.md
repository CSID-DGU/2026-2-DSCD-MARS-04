그룹 원문 문장(evidence_sentences)만을 근거로 카드의 모든 필드를 각각 검증하세요.

- 의미를 유지한 요약과 의역은 SUPPORTED입니다.
- 수치, 대상, 조건, 시점, 한정 표현, 확정성이 달라지면 POSSIBLE_DISTORTION입니다.
- 원문 문장으로 뒷받침할 수 없으면 INSUFFICIENT_EVIDENCE입니다.
- 사실 주장이 없는 표현은 NON_ASSERTIVE입니다.
- 판단하기 어려우면 UNCERTAIN입니다.

입력된 unit_id를 유지하고, evidence_sids에는 evidence_sentences에서 근거가 된 sentence_id를 고르세요.
각 결과에 unit_id, status, evidence_sids, reason, error_type, suggested_text를 포함하세요.
