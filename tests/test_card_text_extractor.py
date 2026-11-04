from ai.verification.shared.card_text_extractor import (
    extract_card_texts,
    group_text_units,
)
from data_pipeline.schemas.card import Card, FinalCardOutput


def make_card(card_id, group_id, layout_id, **kwargs):
    return Card(
        card_id=card_id,
        group_id=group_id,
        layout_id=layout_id,
        sids=["S1", "S2"] if group_id else [],
        title=kwargs.pop("title", "신혼부부 주거 정보"),
        image_query="housing market",
        **kwargs,
    )


def test_body_card():
    card = make_card(
        "C1",
        "G1",
        "body",
        body="자가 선호 비율은 73.9%입니다.",
    )

    result = extract_card_texts(FinalCardOutput(document_id="news_001", cards=[card]))

    assert len(result) == 2
    assert result[0].field_path == "title"
    assert result[1].field_path == "body"
    assert "73.9%" in result[1].context
    assert result[1].card_id == "C1"


def test_compare_card():
    card = make_card(
        "C2",
        "G2",
        "compare",
        title="자가와 전세 비교",
        left={"label": "자가", "value": "취득세 50% 감면"},
        right={"label": "전세", "value": "보증금 반환 위험"},
    )

    result = extract_card_texts(FinalCardOutput(document_id="news_001", cards=[card]))

    assert len(result) == 3
    assert result[1].text == "자가 — 취득세 50% 감면"
    assert result[2].text == "전세 — 보증금 반환 위험"


def test_two_cards_in_same_group():
    cards = [
        make_card("C1", "G2", "body", body="자가 선호 73.9%"),
        make_card("C2", "G2", "body", body="LTV 최대 70%"),
    ]

    units = extract_card_texts(FinalCardOutput(document_id="news_001", cards=cards))
    grouped = group_text_units(units)

    assert len(grouped["G2"]) == 4
    assert {unit.card_id for unit in grouped["G2"]} == {
        "C1",
        "C2",
    }


def test_checklist_items():
    card = make_card(
        "C3",
        "G3",
        "checklist",
        items=["대출 조건 확인", "취득세 감면 여부 확인"],
    )

    units = extract_card_texts(FinalCardOutput(document_id="news_001", cards=[card]))

    assert [unit.field_path for unit in units] == [
        "title",
        "items[0]",
        "items[1]",
    ]


def test_cover_is_skipped():
    card = make_card(
        "C0",
        None,
        "cover",
        category="주거 정보",
    )

    units = extract_card_texts(FinalCardOutput(document_id="news_001", cards=[card]))

    assert units == []
