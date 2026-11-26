from ai.verification.factuality.hybrid.evidence_matcher import (
    EvidenceCandidate,
    EvidenceMatch,
    EvidenceSentence,
)
from ai.verification.factuality.hybrid.rule_checks import (
    check_rule_risks,
    extract_measurements,
)
from ai.verification.shared.card_text_extractor import CardTextUnit


def make_match(card_text, evidence_text):
    """Create a card-evidence pair for rule testing."""

    unit = CardTextUnit(
        unit_id="C1:body",
        card_id="C1",
        group_id="G1",
        layout_id="body",
        field_path="body",
        text=card_text,
        context=card_text,
        sids=("S1",),
    )

    evidence = EvidenceSentence(
        evidence_id="G1_E1",
        group_id="G1",
        text=evidence_text,
    )

    return EvidenceMatch(
        unit=unit,
        candidates=(
            EvidenceCandidate(
                evidence=evidence,
                score=0.9,
            ),
        ),
    )


# 기존 테스트 7개


def test_number_mismatch():
    match = make_match(
        "LTV 최대 90% 적용",
        "LTV 최대 70% 적용",
    )

    flags = check_rule_risks(match)

    assert len(flags) == 1
    assert flags[0].risk_type == "NUMBER_MISMATCH"


def test_correct_number():
    match = make_match(
        "LTV 최대 70% 적용",
        "LTV 최대 70% 적용",
    )

    assert check_rule_risks(match) == []


def test_qualifier_mismatch():
    match = make_match(
        "LTV 70% 이상 적용",
        "LTV 최대 70% 적용",
    )

    flags = check_rule_risks(match)

    assert len(flags) == 1
    assert flags[0].risk_type == "QUALIFIER_MISMATCH"


def test_number_normalization():
    match = make_match(
        "승용 보조금은 1800만원이다.",
        "승용 보조금은 1,800만원이다.",
    )

    assert check_rule_risks(match) == []


def test_extra_evidence_numbers_are_allowed():
    match = make_match(
        "총 196대 지원",
        "총 196대, 일반 176대, 취약계층 20대 지원",
    )

    assert check_rule_risks(match) == []


def test_extract_multiple_measurements():
    result = extract_measurements("승용 최대 1800만원, 초소형 870만원 지원")

    assert len(result) == 2
    assert result[0].qualifier == "최대"
    assert result[1].qualifier is None


def test_no_evidence_is_not_a_mismatch():
    match = make_match(
        "LTV 최대 70%",
        "LTV 최대 70%",
    )

    empty_match = EvidenceMatch(
        unit=match.unit,
        candidates=(),
    )

    assert check_rule_risks(empty_match) == []


# 신규 테스트 3개: 대상-수치 관계 검증


def test_matches_amount_to_correct_subject():
    """초소형 보조금은 승용 금액이 아닌 초소형 금액과 비교."""

    match = make_match(
        "초소형 전기자동차 보조금은 970만원이다.",
        "승용은 최대 1800만원, 초소형은 870만원을 지급한다.",
    )

    flags = check_rule_risks(match)

    assert any(flag.risk_type == "NUMBER_MISMATCH" and "870만원" in flag.detail for flag in flags)


def test_subject_value_swap():
    """수치가 모두 존재하더라도 대상과 값이 뒤바뀌면 탐지."""

    match = make_match(
        "개인은 최대 3대, 사업자는 1대를 지원받는다.",
        "개인은 1대, 사업자는 최대 3대를 지원받는다.",
    )

    flags = check_rule_risks(match)

    assert flags
    assert any(
        flag.risk_type
        in {
            "NUMBER_MISMATCH",
            "QUALIFIER_MISMATCH",
        }
        for flag in flags
    )


def test_correct_subject_value_pair():
    """다른 대상의 수치가 함께 있어도 올바른 관계라면 정상."""

    match = make_match(
        "초소형 전기자동차 보조금은 870만원이다.",
        "승용은 최대 1800만원, 초소형은 870만원을 지급한다.",
    )

    flags = check_rule_risks(match)

    assert flags == []
