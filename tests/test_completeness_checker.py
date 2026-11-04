from ai.verification.factuality.hybrid.checker import (
    aggregate_status,
    check_completeness,
    combine_field_status,
)
from data_pipeline.schemas.card import Card, FinalCardOutput
from data_pipeline.schemas.group import Group


def test_supported_status():
    status = combine_field_status(
        ["ENTAILMENT"],
        [],
        has_evidence=True,
    )
    assert status == "SUPPORTED"


def test_contradiction_status():
    status = combine_field_status(
        ["CONTRADICTION"],
        [],
        has_evidence=True,
    )
    assert status == "POSSIBLE_DISTORTION"


def test_neutral_status():
    status = combine_field_status(
        ["NEUTRAL"],
        [],
        has_evidence=True,
    )
    assert status == "INSUFFICIENT_EVIDENCE"


def test_conflicting_evidence_is_uncertain():
    status = combine_field_status(
        ["ENTAILMENT", "CONTRADICTION"],
        [],
        has_evidence=True,
    )
    assert status == "UNCERTAIN"


def test_missing_evidence_is_uncertain():
    status = combine_field_status(
        [],
        [],
        has_evidence=False,
    )
    assert status == "UNCERTAIN"


def test_aggregate_status():
    assert aggregate_status(["SUPPORTED", "POSSIBLE_DISTORTION"]) == "POSSIBLE_DISTORTION"


def test_end_to_end_two_cards_one_group():
    group = Group(
        group_id="G2",
        sentence_ids=["S1", "S2"],
        topic="신혼부부 주택 구입 혜택",
        headline="신혼부부를 위한 대출 및 취득세 혜택",
        summary=("신혼부부의 LTV는 최대 70%까지 적용된다. 생애 최초 주택 취득세는 50% 감면된다."),
    )

    cards = FinalCardOutput(
        document_id="news_001",
        cards=[
            Card(
                card_id="C1",
                group_id="G2",
                layout_id="body",
                sids=["S1"],
                title="주택 구입 대출 혜택",
                body="LTV 최대 70% 적용",
                image_query="housing loan",
            ),
            Card(
                card_id="C2",
                group_id="G2",
                layout_id="body",
                sids=["S2"],
                title="신혼부부 취득세 감면",
                body="취득세 50% 감면",
                image_query="housing tax",
            ),
        ],
    )

    def fake_predictor(premise, hypothesis):
        return {
            "ENTAILMENT": 0.98,
            "NEUTRAL": 0.01,
            "CONTRADICTION": 0.01,
        }

    result = check_completeness(
        groups=[group],
        final_cards=cards,
        predictor=fake_predictor,
    )

    assert result.document_id == "news_001"
    assert len(result.cards) == 2
    assert {card.card_id for card in result.cards} == {
        "C1",
        "C2",
    }
    assert all(card.group_id == "G2" for card in result.cards)
    assert all(card.fields for card in result.cards)
