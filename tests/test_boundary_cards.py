import pytest

from ai.generation.card_checks import validate_boundary_output
from ai.generation.layout_loader import load_all_layout_options
from data_pipeline.schemas.card import CardGenerationInput, CardGenerationOutput
from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import LayoutSelection


def request() -> CardGenerationInput:
    return CardGenerationInput(
        document_id="news_001",
        groups=[
            Group(
                group_id="G1",
                sentence_ids=["S1"],
                summary="청년 지원금이 월 20만 원으로 늘어난다.",
                topic="청년 지원금",
                headline="월 지원금 인상",
            )
        ],
        layout_selections=[LayoutSelection(group_id="G1", layout_id="body")],
        available_layouts=load_all_layout_options("data/layouts.json"),
    )


def result(*, cover_title="청년 지원금이 늘어납니다") -> CardGenerationOutput:
    return CardGenerationOutput.model_validate(
        {
            "document_id": "news_001",
            "cards": [
                {
                    "group_id": None,
                    "layout_id": "cover",
                    "sids": [],
                    "title": cover_title,
                    "category": "청년 지원",
                    "image_query": "youth savings plan",
                },
                {
                    "group_id": None,
                    "layout_id": "closing",
                    "sids": [],
                    "title": "달라진 지원금을 확인하세요",
                    "body": "지원 대상과 적용 시점을 기사에서 다시 확인해 보세요.",
                    "cta": "지원 내용 확인",
                    "image_query": "reading policy news",
                },
            ],
        }
    )


def test_generated_cover_and_closing_satisfy_fixed_layouts():
    validate_boundary_output(request(), result())


def test_boundary_cards_must_keep_cover_closing_order():
    generated = result()
    generated.cards.reverse()

    with pytest.raises(ValueError, match="순서대로"):
        validate_boundary_output(request(), generated)


def test_generated_copy_must_fit_fixed_layout_limits():
    with pytest.raises(ValueError, match="글자 수 초과"):
        validate_boundary_output(request(), result(cover_title="가" * 29))
