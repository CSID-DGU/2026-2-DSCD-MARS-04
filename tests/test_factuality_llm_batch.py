from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ai.verification.factuality.llm.llm_checker import (
    LLMCardResponse,
    LLMJudgment,
    verify_card,
)
from ai.verification.shared.card_text_extractor import CardTextUnit
from data_pipeline.schemas.card import Card


def make_units():
    return [
        CardTextUnit(
            unit_id="C1:title",
            card_id="C1",
            group_id="G1",
            layout_id="body",
            field_path="title",
            text="전기자동차 보조금 안내",
            context="전기자동차 보조금 안내",
            sids=("S1",),
        ),
        CardTextUnit(
            unit_id="C1:body",
            card_id="C1",
            group_id="G1",
            layout_id="body",
            field_path="body",
            text="아산시는 전기차 196대를 지원할 예정이다.",
            context="아산시는 전기차 196대를 지원할 예정이다.",
            sids=("S1",),
        ),
    ]


def make_card():
    return Card(
        card_id="C1",
        group_id="G1",
        layout_id="body",
        sids=["S1"],
        title="전기자동차 보조금 안내",
        body="아산시는 전기차 196대를 지원할 예정이다.",
        image_query="electric car",
    )


def make_response():
    return LLMCardResponse(
        results=[
            LLMJudgment(
                unit_id="C1:title",
                status="NON_ASSERTIVE",
                evidence="",
                reason="주제형 제목입니다.",
                error_type=None,
                suggested_text=None,
            ),
            LLMJudgment(
                unit_id="C1:body",
                status="SUPPORTED",
                evidence="아산시는 전기차 196대를 지원할 예정이다.",
                reason="근거와 일치합니다.",
                error_type=None,
                suggested_text=None,
            ),
        ]
    )


def test_one_api_call_for_multiple_fields():
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=make_response(),
        usage=SimpleNamespace(
            input_tokens=500,
            output_tokens=100,
        ),
    )

    results, input_tokens, output_tokens = verify_card(
        card=make_card(),
        units=make_units(),
        summary="아산시는 전기차 196대를 지원할 예정이다.",
        client=client,
        model="gpt-4.1-mini",
    )

    assert client.responses.parse.call_count == 1
    assert len(results) == 2
    assert results[0].field_path == "title"
    assert results[0].status == "NON_ASSERTIVE"
    assert results[1].field_path == "body"
    assert results[1].status == "SUPPORTED"
    assert input_tokens == 500
    assert output_tokens == 100


def test_missing_field_result_is_rejected():
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=LLMCardResponse(
            results=[
                LLMJudgment(
                    unit_id="C1:title",
                    status="NON_ASSERTIVE",
                    evidence="",
                    reason="주제형 제목입니다.",
                    error_type=None,
                    suggested_text=None,
                )
            ]
        ),
        usage=None,
    )

    with pytest.raises(ValueError):
        verify_card(
            card=make_card(),
            units=make_units(),
            summary="아산시는 전기차 196대를 지원할 예정이다.",
            client=client,
            model="gpt-4.1-mini",
        )


def test_duplicate_field_result_is_rejected():
    client = MagicMock()
    response = make_response()

    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=LLMCardResponse(
            results=[
                response.results[0],
                response.results[0],
            ]
        ),
        usage=None,
    )

    with pytest.raises(ValueError):
        verify_card(
            card=make_card(),
            units=make_units(),
            summary="아산시는 전기차 196대를 지원할 예정이다.",
            client=client,
            model="gpt-4.1-mini",
        )


def test_invalid_evidence_becomes_uncertain():
    client = MagicMock()
    response = make_response()

    response.results[1].evidence = "요약문에 없는 근거입니다."

    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=response,
        usage=None,
    )

    results, _, _ = verify_card(
        card=make_card(),
        units=make_units(),
        summary="아산시는 전기차 196대를 지원할 예정이다.",
        client=client,
        model="gpt-4.1-mini",
    )

    assert results[1].status == "UNCERTAIN"
    assert results[1].evidence == ""
