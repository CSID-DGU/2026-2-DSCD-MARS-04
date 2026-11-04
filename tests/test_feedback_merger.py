from types import SimpleNamespace

import pytest

from ai.verification.feedback.merger import (
    FeedbackItem,
    FeedbackResponse,
    collect_findings,
    determine_status,
    validate_feedback,
)


def make_results():
    factuality = SimpleNamespace(
        cards=[
            SimpleNamespace(
                card_id="C4",
                status="POSSIBLE_DISTORTION",
                fields=[
                    SimpleNamespace(
                        unit_id="C4:body",
                        card_id="C4",
                        status="POSSIBLE_DISTORTION",
                        card_text="초소형 보조금은 970만원이다.",
                        evidence="초소형은 870만원을 지급한다.",
                        reason="보조금 수치가 다릅니다.",
                        suggested_text="초소형 보조금은 870만원이다.",
                    )
                ],
            )
        ],
    )

    completeness = SimpleNamespace(
        status="DISTORTED",
        results=[
            SimpleNamespace(
                fact_id="F2",
                status="DISTORTED",
                matched_card_ids=["C4"],
                reason="선택한 금액이 잘못 반영되었습니다.",
                missing_elements=["870만원"],
            )
        ],
    )

    return factuality, completeness


def test_collect_findings():
    factuality, completeness = make_results()

    findings, unchecked, card_ids = collect_findings(
        factuality,
        completeness,
    )

    assert len(findings) == 2
    assert {item["source_id"] for item in findings} == {
        "F:C4:body",
        "C:F2",
    }
    assert unchecked == []
    assert card_ids == {"C4"}


def test_combined_feedback():
    factuality, completeness = make_results()

    findings, unchecked, card_ids = collect_findings(
        factuality,
        completeness,
    )

    response = FeedbackResponse(
        items=[
            FeedbackItem(
                title="초소형 보조금 수치 오류 의심",
                category="ERROR",
                description="970만원을 870만원으로 수정해야 합니다.",
                suggested_text="초소형 보조금은 870만원이다.",
                source_ids=["F:C4:body", "C:F2"],
                card_ids=["C4"],
            )
        ]
    )

    items = validate_feedback(response, findings, card_ids)

    assert len(items) == 1
    assert determine_status(findings, unchecked) == "ISSUES_FOUND"


def test_missing_source_is_rejected():
    factuality, completeness = make_results()

    findings, _, card_ids = collect_findings(
        factuality,
        completeness,
    )

    response = FeedbackResponse(
        items=[
            FeedbackItem(
                title="보조금 오류",
                category="ERROR",
                description="금액 확인 필요",
                suggested_text=None,
                source_ids=["F:C4:body"],
                card_ids=["C4"],
            )
        ]
    )

    with pytest.raises(ValueError):
        validate_feedback(response, findings, card_ids)
