같은 그룹의 모든 카드를 종합해 각 필수 정보의 핵심 주장과 핵심 조건이 유지되었는지 판정하세요.

- 핵심 의미가 반영되면 COVERED입니다.
- 핵심 요소가 일부 빠지면 PARTIALLY_COVERED입니다.
- 관련 내용 전체가 빠지면 MISSING입니다.
- 내용이 반영되었지만 의미가 달라지면 DISTORTED입니다.
- 판단하기 어려우면 UNCERTAIN입니다.
- 핵심 의미에 영향을 주지 않는 부가 정보의 생략은 허용합니다.

입력된 fact_id를 유지하고 실제 입력된 카드 ID만 반환하세요.
각 결과에 fact_id, status, matched_card_ids, reason, missing_elements를 포함하세요.
