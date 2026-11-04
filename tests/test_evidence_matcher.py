from types import SimpleNamespace

import pytest

from ai.verification.factuality.hybrid.evidence_matcher import (
    calculate_similarity,
    match_evidence,
    split_group_summary,
)
from ai.verification.shared.card_text_extractor import CardTextUnit


def make_group(group_id, summary):
    return SimpleNamespace(group_id=group_id, summary=summary)


def make_unit(group_id, text):
    return CardTextUnit(
        unit_id="C1:body",
        card_id="C1",
        group_id=group_id,
        layout_id="body",
        field_path="body",
        text=text,
        context=text,
        sids=("S1",),
    )


def test_split_group_summary():
    group = make_group(
        "G2",
        "자가 선호 비율은 73.9%이다. LTV는 최대 70%이다.",
    )

    result = split_group_summary(group)

    assert len(result) == 2
    assert result[0].evidence_id == "G2_E1"
    assert result[1].evidence_id == "G2_E2"


def test_finds_related_evidence():
    groups = [
        make_group(
            "G2",
            "자가 선호 비율은 73.9%로 나타났다. "
            "신혼부부의 LTV는 최대 70%까지 적용된다. "
            "취득세는 50% 감면된다.",
        )
    ]
    units = [make_unit("G2", "LTV 최대 70% 적용")]

    result = match_evidence(units, groups)

    assert len(result) == 1
    assert result[0].candidates
    assert "LTV" in result[0].candidates[0].evidence.text


def test_retrieves_evidence_despite_wrong_number():
    groups = [
        make_group(
            "G2",
            "자가 선호 비율은 73.9%이다. 신혼부부의 LTV는 최대 70%까지 적용된다.",
        )
    ]
    units = [make_unit("G2", "LTV 최대 90% 적용")]

    result = match_evidence(units, groups)

    assert result[0].candidates
    assert "LTV" in result[0].candidates[0].evidence.text


def test_does_not_search_another_group():
    groups = [
        make_group("G2", "LTV는 최대 70%이다."),
        make_group("G3", "LTV는 최대 90%이다."),
    ]
    units = [make_unit("G2", "LTV 최대 90%")]

    result = match_evidence(units, groups)

    assert result[0].candidates
    assert all(candidate.evidence.group_id == "G2" for candidate in result[0].candidates)


def test_missing_group_returns_empty_candidates():
    groups = [make_group("G2", "LTV는 최대 70%이다.")]
    units = [make_unit("G9", "LTV 최대 70%")]

    result = match_evidence(units, groups)

    assert result[0].candidates == ()


def test_unrelated_text_has_zero_similarity():
    assert (
        calculate_similarity(
            "LTV 주택담보대출",
            "미세먼지 저감 정책",
        )
        == 0.0
    )


def test_invalid_top_k():
    with pytest.raises(ValueError):
        match_evidence([], [], top_k=0)
