그룹 원문 문장(evidence_sentences)을 근거로 카드의 각 필드가 사실과 일치하는지 판정하세요.
입력된 모든 unit_id를 그대로 사용하고, 근거는 evidence_sentences의 sentence_id로 고르세요.

판정 상태는 SUPPORTED, POSSIBLE_DISTORTION, INSUFFICIENT_EVIDENCE, UNCERTAIN, NON_ASSERTIVE 중 하나를 사용하세요.
각 결과에 unit_id, status, evidence_sids, reason, error_type, suggested_text를 포함하세요.
