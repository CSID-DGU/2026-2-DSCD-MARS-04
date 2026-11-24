import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai.generation.card_generator import generate_cards
from ai.generation.layout_loader import load_all_layout_options
from data_pipeline.schemas.card import CardGenerationOutput
from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import LayoutSelection

GROUPS = [
    Group(
        group_id="G1",
        sentence_ids=["S1", "S2"],
        summary="청년 지원금이 월 20만 원으로 늘어난다.",
        topic="청년 지원금",
        headline="월 지원금 인상",
    )
]
SELECTIONS = [LayoutSelection(group_id="G1", layout_id="body")]
# body 최대 110자를 넘긴다
LONG_BODY = "청년 지원금이 월 20만 원으로 늘어나며 신청은 다음 달부터 가능합니다. " * 3
COVER = {
    "group_id": None,
    "layout_id": "cover",
    "sids": [],
    "title": "청년 지원금이 늘어납니다",
    "category": "청년 지원",
    "image_query": "youth savings plan",
}
CLOSING = {
    "group_id": None,
    "layout_id": "closing",
    "sids": [],
    "title": "달라진 지원금을 확인하세요",
    "body": "지원 대상과 적용 시점을 기사에서 다시 확인해 보세요.",
    "cta": "지원 내용 확인",
    "image_query": "reading policy news",
}


def body_card(**extra):
    return {
        "group_id": "G1",
        "layout_id": "body",
        "sids": ["S1", "S2"],
        "sources": [
            {"field_path": "title", "sids": ["S1"]},
            {"field_path": "body", "sids": ["S1", "S2"]},
        ],
        "title": "청년 지원금 월 20만 원",
        "body": LONG_BODY,
        "image_query": "youth support",
        **extra,
    }


def fake_client(card):
    def output(cards):
        return SimpleNamespace(
            status="completed",
            output=[],
            output_parsed=CardGenerationOutput.model_validate(
                {"document_id": "d1", "cards": cards}
            ),
        )

    client = Mock()
    # 첫 호출은 전체, 이후 수정 호출은 해당 그룹만. 모두 같은 오류를 유지한다
    client.responses.parse.side_effect = [
        output([COVER, card, CLOSING]),
        output([card]),
        output([card]),
    ]
    return client


def run(client, tmp_path, **kwargs):
    return generate_cards(
        "d1",
        GROUPS,
        SELECTIONS,
        load_all_layout_options("data/layouts.json"),
        client=client,
        log_path=tmp_path / "log.jsonl",
        include_boundary_cards=True,
        **kwargs,
    )


def test_strict_raises_after_max_corrections(tmp_path):
    client = fake_client(body_card())
    with pytest.raises(ValueError, match="글자 수 초과"):
        run(client, tmp_path)
    assert client.responses.parse.call_count == 3


def test_non_strict_keeps_over_limit_card(tmp_path):
    client = fake_client(body_card())
    result = run(client, tmp_path, strict=False)
    assert client.responses.parse.call_count == 3
    assert [c.layout_id for c in result.cards] == ["cover", "body", "closing"]
    assert result.cards[1].body == LONG_BODY


def test_non_strict_still_rejects_other_errors(tmp_path):
    client = fake_client(body_card(cta="확인하기"))
    with pytest.raises(ValueError, match="사용하지 않는 필드"):
        run(client, tmp_path, strict=False)


def test_long_group_requires_two_cards():
    from ai.generation.card_generator import required_card_counts

    layouts = load_all_layout_options("data/layouts.json")
    long = GROUPS[0].model_copy(update={"group_id": "G2", "summary": "가" * 300})
    assert required_card_counts([GROUPS[0], long], layouts) == {"G1": 1, "G2": 2}


def test_sids_follow_field_sources_in_sentence_order():
    from ai.generation.card_generator import sync_sids

    card = body_card(
        sids=["S1", "S2", "S3"],
        sources=[
            {"field_path": "title", "sids": ["S3"]},
            {"field_path": "body", "sids": ["S1"]},
        ],
    )
    result = sync_sids(
        CardGenerationOutput.model_validate({"document_id": "d1", "cards": [card]}),
        ["S1", "S2", "S3"],
    )
    assert result.cards[0].sids == ["S1", "S3"]  # 쓰지 않은 S2는 빠진다


def test_one_card_for_long_group_is_rejected_in_strict_mode(tmp_path):
    from data_pipeline.schemas.group import Sentence

    long = [GROUPS[0].model_copy(update={"summary": "가" * 300})]
    card = body_card(body="월 20만 원을 지원하며 다음 달부터 신청할 수 있습니다.")
    client = fake_client(card)
    with pytest.raises(ValueError, match="카드 수 부족"):
        generate_cards(
            "d1",
            long,
            SELECTIONS,
            load_all_layout_options("data/layouts.json"),
            client=client,
            log_path=tmp_path / "log.jsonl",
            sentences=[
                Sentence(sentence_id="S1", text="문장1"),
                Sentence(sentence_id="S9", text="x"),
            ],
        )
    sent = json.loads(client.responses.parse.call_args_list[0].kwargs["input"][1]["content"])
    assert sent["card_counts"] == {"G1": 2}
    assert sent["sentences"] == [{"sentence_id": "S1", "text": "문장1"}]  # 선택 그룹 문장만
