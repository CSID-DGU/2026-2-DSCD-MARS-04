"""promptfoo 오프라인 평가에서 쓰는 assertion·provider·결과 검증 코드 테스트."""

import json

from experiments.promptfoo.assertions.summary_numbers import (
    keeps_source_numbers,
    no_new_numbers,
)
from experiments.promptfoo.assertions.visual_judgment import valid_visual_judgment
from experiments.promptfoo.providers.replay import call_api
from experiments.promptfoo.scripts.check_results import compare_results

SOURCE = "초소형 전기차 보조금은 최대 870만원이며 총 196대를 지원한다."


def _context(**variables):
    return {"vars": variables}


def test_no_new_numbers_passes_when_numbers_come_from_source():
    result = no_new_numbers("초소형 보조금은 최대 870만원이다.", _context(source=SOURCE))
    assert result["pass"] is True


def test_no_new_numbers_fails_on_changed_number():
    result = no_new_numbers("초소형 보조금은 최대 970만원이다.", _context(source=SOURCE))
    assert result["pass"] is False
    assert "970" in result["reason"]


def test_keeps_source_numbers_fails_when_number_is_dropped():
    result = keeps_source_numbers("초소형 보조금은 최대 870만원이다.", _context(source=SOURCE))
    assert result["pass"] is False
    assert "196" in result["reason"]


def test_keeps_source_numbers_passes_when_all_numbers_kept():
    output = "보조금은 최대 870만원, 총 196대를 지원한다."
    assert keeps_source_numbers(output, _context(source=SOURCE))["pass"] is True


VISUAL_VARS = {
    "card_ids": ["C1", "C2"],
    "criteria": ["hierarchy", "image_contribution"],
}


def _visual(judgments):
    return json.dumps({"judgments": judgments}, ensure_ascii=False)


def test_valid_visual_judgment_accepts_complete_result():
    output = _visual(
        [
            {
                "criterion_id": "hierarchy",
                "scope": "card",
                "card_ids": ["C1"],
                "verdict": "MET",
                "evidence": "제목이 본문보다 크다",
                "reason": "핵심 메시지가 먼저 보인다",
            },
            {
                "criterion_id": "image_contribution",
                "scope": "card",
                "card_ids": ["C2"],
                "verdict": "NOT_APPLICABLE",
                "evidence": "",
                "reason": "이미지가 없는 체크리스트 카드",
            },
        ]
    )
    assert valid_visual_judgment(output, _context(**VISUAL_VARS))["pass"] is True


def test_valid_visual_judgment_rejects_unknown_card_and_missing_criterion():
    output = _visual(
        [
            {
                "criterion_id": "hierarchy",
                "scope": "card",
                "card_ids": ["C9"],
                "verdict": "MET",
                "evidence": "x",
                "reason": "x",
            }
        ]
    )
    result = valid_visual_judgment(output, _context(**VISUAL_VARS))
    assert result["pass"] is False
    assert "C9" in result["reason"]
    assert "image_contribution" in result["reason"]


def test_valid_visual_judgment_requires_reason_for_not_applicable():
    output = _visual(
        [
            {
                "criterion_id": "hierarchy",
                "scope": "card",
                "card_ids": ["C1"],
                "verdict": "NOT_APPLICABLE",
                "evidence": "",
                "reason": "",
            },
            {
                "criterion_id": "image_contribution",
                "scope": "card",
                "card_ids": ["C2"],
                "verdict": "GOOD",
                "evidence": "x",
                "reason": "x",
            },
        ]
    )
    result = valid_visual_judgment(output, _context(**VISUAL_VARS))
    assert result["pass"] is False
    assert "GOOD" in result["reason"]
    assert "NOT_APPLICABLE" in result["reason"]


def test_valid_visual_judgment_rejects_non_json():
    assert valid_visual_judgment("좋아 보입니다", _context(**VISUAL_VARS))["pass"] is False


def test_replay_provider_returns_saved_output():
    result = call_api(
        "ignored",
        {"config": {"fixture": "summary_outputs.json", "system": "cardsync_fixture"}},
        {"vars": {"case_id": "smoke_ev_subsidy"}},
    )
    assert "error" not in result
    assert "870" in result["output"]
    assert result["metadata"]["fixture"] is True


def test_replay_provider_reports_missing_case_instead_of_inventing_output():
    result = call_api(
        "ignored",
        {"config": {"fixture": "summary_outputs.json", "system": "cardsync_fixture"}},
        {"vars": {"case_id": "does_not_exist"}},
    )
    assert "error" in result
    assert "output" not in result


def _row(case_id, provider, metric, passed):
    return {
        "vars": {"case_id": case_id},
        "provider": {"label": provider},
        "gradingResult": {"componentResults": [{"pass": passed, "assertion": {"metric": metric}}]},
    }


def test_compare_results_reports_mismatch_and_missing_expectation():
    expected = {
        ("a", "p", "m1"): True,
        ("a", "p", "m2"): False,
    }
    rows = [_row("a", "p", "m1", False)]
    problems = compare_results(rows, expected)
    assert any("m1" in p for p in problems)
    assert any("m2" in p for p in problems)


def test_compare_results_accepts_exact_match():
    expected = {("a", "p", "m1"): False}
    assert compare_results([_row("a", "p", "m1", False)], expected) == []
