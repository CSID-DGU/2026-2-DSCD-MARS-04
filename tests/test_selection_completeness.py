import json
from types import SimpleNamespace

import pytest

from ai.verification.completeness.llm.llm_checker import (
    CoverageResponse,
    FactJudgment,
    RequiredFact,
    build_required_facts,
    check_llm_completeness,
)
from data_pipeline.schemas.card import Card, FinalCardOutput
from data_pipeline.schemas.group import Group


def groups():
    return [
        Group(
            group_id=f"G{i}",
            sentence_ids=[f"S{i}"],
            summary=summary,
            topic="지원",
            headline="지원 안내",
        )
        for i, summary in enumerate(
            [
                "총 196대, 일반 176대와 취약계층 20대 지원.",
                "초소형 보조금은 870만원이다.",
            ],
            start=1,
        )
    ]


def test_selection_preserves_full_summary_and_order():
    source = groups()

    facts = build_required_facts(source, ["G2", "G1"])

    assert [fact.fact_id for fact in facts] == [
        "G2:summary",
        "G1:summary",
    ]

    assert [fact.group_id for fact in facts] == [
        "G2",
        "G1",
    ]

    assert [fact.text for fact in facts] == [
        source[1].summary,
        source[0].summary,
    ]


def test_default_selection_includes_all_groups():
    source = groups()

    facts = build_required_facts(source)

    assert len(facts) == 2

    assert [fact.fact_id for fact in facts] == [
        "G1:summary",
        "G2:summary",
    ]

    assert [fact.text for fact in facts] == [
        source[0].summary,
        source[1].summary,
    ]


@pytest.mark.parametrize(
    "ids",
    [
        ["G3"],
        ["G1", "G1"],
    ],
)
def test_invalid_selection(ids):
    with pytest.raises(ValueError):
        build_required_facts(groups(), ids)


def test_empty_selection():
    facts = build_required_facts(groups(), [])

    assert facts == []


def test_empty_selection_returns_not_checked():
    result = check_llm_completeness(
        groups(),
        FinalCardOutput(
            document_id="test",
            cards=[],
        ),
        required_group_ids=[],
    )

    assert result.status == "NOT_CHECKED"
    assert result.results == ()
    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_duplicate_group_ids():
    source = groups()
    duplicated = [source[0], source[0]]

    with pytest.raises(ValueError):
        build_required_facts(duplicated)


def test_empty_group_summary():
    source = groups()
    source[0].summary = "   "

    with pytest.raises(ValueError):
        build_required_facts(source, ["G1"])


def test_missing_selected_group_has_missing_result_without_api():
    result = check_llm_completeness(
        groups(),
        FinalCardOutput(
            document_id="test",
            cards=[],
        ),
    )

    assert result.status == "MISSING"

    assert [result_item.fact_id for result_item in result.results] == [
        "G1:summary",
        "G2:summary",
    ]

    assert all(result_item.status == "MISSING" for result_item in result.results)

    assert all(result_item.matched_card_ids == [] for result_item in result.results)

    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_default_auto_coverage_and_selected_scope():
    payloads = []

    def parse(**kwargs):
        payload = json.loads(kwargs["input"])
        payloads.append(payload)

        fact = payload["required_facts"][0]

        return SimpleNamespace(
            output_parsed=CoverageResponse(
                results=[
                    FactJudgment(
                        fact_id=fact["fact_id"],
                        status="PARTIALLY_COVERED",
                        matched_card_ids=["C1"],
                        reason="핵심 지원 수량의 세부 구분이 누락되었습니다.",
                        missing_elements=["일반 176대와 취약계층 20대"],
                    )
                ]
            ),
            usage=None,
        )

    cards = FinalCardOutput(
        document_id="test",
        cards=[
            Card(
                card_id="C1",
                group_id="G1",
                layout_id="body",
                sids=["S1"],
                title="지원",
                body="총 196대 지원.",
                image_query="car",
            )
        ],
    )

    result = check_llm_completeness(
        groups(),
        cards,
        required_group_ids=["G1"],
        client=SimpleNamespace(responses=SimpleNamespace(parse=parse)),
    )

    assert result.status == "PARTIALLY_COVERED"
    assert len(result.results) == 1
    assert result.results[0].fact_id == "G1:summary"
    assert result.results[0].matched_card_ids == ["C1"]

    assert len(payloads) == 1
    assert payloads[0]["group_id"] == "G1"
    assert len(payloads[0]["required_facts"]) == 1

    assert payloads[0]["required_facts"][0]["text"] == groups()[0].summary

    assert [card["card_id"] for card in payloads[0]["cards"]] == ["C1"]


def test_explicit_facts_remain_supported():
    fact = RequiredFact(
        fact_id="F1",
        group_id="G2",
        text="870만원",
    )

    result = check_llm_completeness(
        groups(),
        FinalCardOutput(
            document_id="test",
            cards=[],
        ),
        [fact],
    )

    assert [item.fact_id for item in result.results] == ["F1"]
    assert result.status == "MISSING"

    with pytest.raises(ValueError):
        check_llm_completeness(
            groups(),
            FinalCardOutput(
                document_id="test",
                cards=[],
            ),
            [fact],
            required_group_ids=["G1"],
        )


def test_multi_sentence_summary_keeps_conditions_and_url():
    source = groups()[0]

    source.summary = (
        "신청 대상은 공고일 전일까지 주소를 둔 시민이다. 접수는 www.ev.or.kr/ps에서 한다."
    )

    facts = build_required_facts([source])

    assert len(facts) == 1
    assert facts[0].fact_id == "G1:summary"
    assert facts[0].group_id == "G1"
    assert facts[0].text == source.summary

    assert "공고일 전일까지" in facts[0].text
    assert "www.ev.or.kr/ps" in facts[0].text


def test_selected_group_without_cards_returns_missing():
    source = groups()

    cards = FinalCardOutput(
        document_id="test",
        cards=[
            Card(
                card_id="C1",
                group_id="G1",
                layout_id="body",
                sids=["S1"],
                title="지원",
                body="총 196대 지원.",
                image_query="car",
            )
        ],
    )

    result = check_llm_completeness(
        source,
        cards,
        required_group_ids=["G2"],
    )

    assert result.status == "MISSING"
    assert len(result.results) == 1
    assert result.results[0].fact_id == "G2:summary"
    assert result.results[0].status == "MISSING"
    assert result.results[0].matched_card_ids == []
    assert result.input_tokens == 0
    assert result.output_tokens == 0
