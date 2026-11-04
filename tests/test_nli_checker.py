from ai.verification.factuality.hybrid.evidence_matcher import (
    EvidenceCandidate,
    EvidenceMatch,
    EvidenceSentence,
)
from ai.verification.factuality.hybrid.nli_checker import check_nli
from ai.verification.shared.card_text_extractor import CardTextUnit


def make_match(card_text, evidence_texts):
    unit = CardTextUnit(
        unit_id="C1:body",
        card_id="C1",
        group_id="G2",
        layout_id="body",
        field_path="body",
        text=card_text,
        context=card_text,
        sids=("S1",),
    )

    candidates = tuple(
        EvidenceCandidate(
            evidence=EvidenceSentence(
                evidence_id=f"G2_E{index}",
                group_id="G2",
                text=text,
            ),
            score=0.8,
        )
        for index, text in enumerate(evidence_texts, start=1)
    )

    return EvidenceMatch(unit=unit, candidates=candidates)


def test_entailment():
    match = make_match(
        "LTV 최대 70%",
        ["신혼부부의 LTV는 최대 70%이다."],
    )

    def predictor(premise, hypothesis):
        assert "70%" in premise
        assert hypothesis == "LTV 최대 70%"
        return {
            "ENTAILMENT": 0.98,
            "NEUTRAL": 0.01,
            "CONTRADICTION": 0.01,
        }

    result = check_nli(match, predictor=predictor)

    assert result.card_id == "C1"
    assert result.evidence_results[0].label == "ENTAILMENT"
    assert result.evidence_results[0].evidence_id == "G2_E1"


def test_contradiction():
    match = make_match(
        "LTV 최대 90%",
        ["신혼부부의 LTV는 최대 70%이다."],
    )

    def predictor(premise, hypothesis):
        return {
            "ENTAILMENT": 0.001,
            "NEUTRAL": 0.002,
            "CONTRADICTION": 0.997,
        }

    result = check_nli(match, predictor=predictor)

    assert result.evidence_results[0].label == "CONTRADICTION"


def test_keeps_multiple_evidence_results():
    match = make_match(
        "신혼부부 대출 혜택",
        [
            "신혼부부는 소득에 따라 대출받을 수 있다.",
            "주택가격은 하락할 가능성이 있다.",
        ],
    )

    def predictor(premise, hypothesis):
        if "대출" in premise:
            return {
                "ENTAILMENT": 0.9,
                "NEUTRAL": 0.08,
                "CONTRADICTION": 0.02,
            }
        return {
            "ENTAILMENT": 0.01,
            "NEUTRAL": 0.98,
            "CONTRADICTION": 0.01,
        }

    result = check_nli(match, predictor=predictor)

    assert len(result.evidence_results) == 2
    assert result.evidence_results[0].label == "ENTAILMENT"
    assert result.evidence_results[1].label == "NEUTRAL"


def test_no_evidence():
    match = make_match("LTV 최대 70%", [])

    result = check_nli(match)

    assert result.evidence_results == ()


def test_invalid_nli_input():
    match = make_match("LTV 최대 70%", ["근거 문장"])

    def predictor(premise, hypothesis):
        raise ValueError("입력 길이 초과")

    result = check_nli(match, predictor=predictor)

    assert result.evidence_results[0].status == "INPUT_ERROR"
    assert result.evidence_results[0].label == "UNAVAILABLE"
