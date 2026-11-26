from collections import Counter

from ai.verification.completeness.llm.llm_checker import (
    RequiredFact,
    check_llm_completeness,
)
from ai.verification.factuality.llm.llm_checker import (
    check_llm_factuality,
)
from ai.verification.feedback.merger import merge_feedback
from data_pipeline.schemas.card import Card, FinalCardOutput
from data_pipeline.schemas.group import Group


def build_test_data():
    groups = [
        Group(
            group_id="G2",
            sentence_ids=["S3", "S4"],
            topic="아산시 전기자동차 지원",
            headline="전기자동차 보조금 지원 안내",
            summary=(
                "아산시는 올해 전기자동차 총 196대"
                "(일반 176대, 사회취약계층 20대)를 "
                "지원할 예정이다. "
                "구매보조금으로 승용은 최대 1800만원, "
                "초소형은 870만원을 지급한다."
            ),
        )
    ]

    cards = FinalCardOutput(
        document_id="pipeline_test_001",
        cards=[
            Card(
                card_id="C3",
                group_id="G2",
                layout_id="body",
                sids=["S3"],
                title="아산시 전기자동차 지원",
                body=("아산시는 올해 전기자동차 총 196대를 지원할 예정이다."),
                image_query="electric vehicle",
            ),
            Card(
                card_id="C4",
                group_id="G2",
                layout_id="body",
                sids=["S4"],
                title="초소형 전기자동차 보조금",
                body="초소형 전기자동차 보조금은 970만원이다.",
                image_query="small electric car",
            ),
        ],
    )

    required_facts = [
        RequiredFact(
            fact_id="F1",
            group_id="G2",
            text="아산시는 올해 전기자동차 총 196대를 지원할 예정이다.",
        ),
        RequiredFact(
            fact_id="F2",
            group_id="G2",
            text="초소형 전기자동차 보조금은 870만원이다.",
        ),
        RequiredFact(
            fact_id="F3",
            group_id="G2",
            text="일반 176대와 사회취약계층 20대를 지원한다.",
        ),
    ]

    return groups, cards, required_facts


def print_factuality(result):
    print("\n========== 사실성 검사 ==========")
    print("전체 상태:", result.status)

    for card in result.cards:
        print(f"\n[{card.card_id}] {card.status}")

        for field in card.fields:
            print(f"  {field.field_path}: {field.status}")
            print(f"  문구: {field.card_text}")
            print(f"  이유: {field.reason}")

            if field.evidence:
                print(f"  근거: {field.evidence}")

            if field.suggested_text:
                print(f"  수정안: {field.suggested_text}")

    print(f"\n토큰: 입력 {result.input_tokens:,}, 출력 {result.output_tokens:,}")


def print_completeness(result):
    print("\n========== 완전성 검사 ==========")
    print("전체 상태:", result.status)

    for fact in result.results:
        print(f"\n[{fact.fact_id}] {fact.status}")
        print("관련 카드:", fact.matched_card_ids)
        print("이유:", fact.reason)
        print("누락·변경 요소:", fact.missing_elements)

    print(f"\n토큰: 입력 {result.input_tokens:,}, 출력 {result.output_tokens:,}")


def print_feedback(result):
    print("\n========== 통합 피드백 ==========")
    print("전체 상태:", result.status)
    print("미검사 항목:", list(result.unchecked))

    for index, item in enumerate(result.items, start=1):
        print(f"\n[{index}] {item.title}")
        print("유형:", item.category)
        print("설명:", item.description)
        print("관련 카드:", item.card_ids)
        print("원본 검사 ID:", item.source_ids)
        print("수정 제안:", item.suggested_text)

    print(f"\n토큰: 입력 {result.input_tokens:,}, 출력 {result.output_tokens:,}")


def inspect_results(factuality, completeness, feedback):
    print("\n========== 결과 점검 ==========")

    field_results = {
        (card.card_id, field.field_path): field
        for card in factuality.cards
        for field in card.fields
    }

    fact_results = {fact.fact_id: fact for fact in completeness.results}

    expected = {
        "C3 본문": (
            field_results.get(("C3", "body")),
            "SUPPORTED",
        ),
        "C4 본문": (
            field_results.get(("C4", "body")),
            "POSSIBLE_DISTORTION",
        ),
        "F1": (fact_results.get("F1"), "COVERED"),
        "F2": (fact_results.get("F2"), "DISTORTED"),
        "F3": (fact_results.get("F3"), "MISSING"),
    }

    for name, (result, expected_status) in expected.items():
        actual = result.status if result is not None else "NOT_FOUND"
        comparison = "일치" if actual == expected_status else "확인 필요"
        print(f"{name}: 기대={expected_status}, 실제={actual} [{comparison}]")

    source_counts = Counter(source_id for item in feedback.items for source_id in item.source_ids)

    assert all(count == 1 for count in source_counts.values())

    factuality_sources = {
        f"F:{field.unit_id}"
        for card in factuality.cards
        for field in card.fields
        if field.status
        in {
            "POSSIBLE_DISTORTION",
            "INSUFFICIENT_EVIDENCE",
            "UNCERTAIN",
        }
    }

    completeness_sources = {
        f"C:{fact.fact_id}"
        for fact in completeness.results
        if fact.status
        in {
            "DISTORTED",
            "PARTIALLY_COVERED",
            "MISSING",
            "UNCERTAIN",
        }
    }

    assert set(source_counts) == (factuality_sources | completeness_sources)

    overlapping_items = [
        item
        for item in feedback.items
        if "F:C4:body" in item.source_ids and "C:F2" in item.source_ids
    ]

    if "F:C4:body" in factuality_sources and "C:F2" in completeness_sources:
        print(
            "C4 오류 중복 통합:",
            "성공" if overlapping_items else "별도 피드백으로 반환됨",
        )

    print("원본 검사 결과 ID 보존: 통과")


def main():
    groups, cards, required_facts = build_test_data()

    print("CardSync 전체 검증 파이프라인 테스트")
    print(f"그룹: {len(groups)}개")
    print(f"카드: {len(cards.cards)}장")
    print(f"필수 정보: {len(required_facts)}개")

    factuality = check_llm_factuality(
        groups=groups,
        final_cards=cards,
    )

    print_factuality(factuality)

    completeness = check_llm_completeness(
        groups=groups,
        final_cards=cards,
        required_facts=required_facts,
    )

    print_completeness(completeness)

    feedback = merge_feedback(
        factuality=factuality,
        completeness=completeness,
    )

    print_feedback(feedback)
    inspect_results(factuality, completeness, feedback)

    total_input_tokens = factuality.input_tokens + completeness.input_tokens + feedback.input_tokens
    total_output_tokens = (
        factuality.output_tokens + completeness.output_tokens + feedback.output_tokens
    )

    print("\n========== 전체 API 사용량 ==========")
    print("입력 토큰:", f"{total_input_tokens:,}")
    print("출력 토큰:", f"{total_output_tokens:,}")
    print("합계:", f"{total_input_tokens + total_output_tokens:,}")


if __name__ == "__main__":
    main()
