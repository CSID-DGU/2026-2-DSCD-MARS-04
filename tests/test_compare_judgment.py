"""완성 카드 비교(CardSync vs 망고보드) 판정 assertion·provider·내보내기 테스트. API 호출 없음."""

import json
from pathlib import Path

from experiments.promptfoo.assertions.compare_judgment import (
    agreement,
    check_judgments,
    human_agreement,
    valid_compare_judgment,
)
from experiments.promptfoo.compare.common import (
    ai_questions,
    expected_keys,
    load_facts,
    load_questions,
)
from experiments.promptfoo.providers.compare_judge import build_instructions, call_api
from experiments.promptfoo.scripts.export_compare import summarize, to_records

FIXTURE = Path("experiments/promptfoo/fixtures/compare_fixtures.json")
SOURCE = "아산시는 전기차 196대를 지원하며 초소형 보조금은 최대 870만원이다."
CARDS = ["C1", "C2"]
FACTS = ["F1", "F2"]


def _fixture(case_id: str) -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))[case_id]["CardSync"]["judgments"]


def _context(**extra):
    vars_ = {"source": SOURCE, "card_ids": json.dumps(CARDS), "fact_ids": json.dumps(FACTS)}
    vars_.update(extra)
    return {"vars": vars_}


def test_questions_have_unique_ids_and_known_kinds():
    spec = load_questions()
    ids = [q["id"] for q in spec["questions"]]
    assert len(ids) == len(set(ids))
    assert {q["kind"] for q in spec["questions"]} <= set(spec["verdicts"]) | {"measure"}


def test_ai_questions_skip_render_only_items():
    ids = {q["id"] for q in ai_questions()}
    assert "D-06" not in ids and "D-07" not in ids
    assert {"C-01", "C-02", "V-01", "S-05"} <= ids


def test_expected_keys_cover_cards_set_and_facts():
    keys = expected_keys(CARDS, FACTS)
    assert ("V-01", "C2", None) in keys
    assert ("S-01", None, None) in keys
    assert ("C-02", None, "F2") in keys
    assert ("C-02", "C1", None) not in keys


def test_valid_fixture_passes():
    output = json.dumps({"judgments": _fixture("smoke_compare_valid")}, ensure_ascii=False)
    assert valid_compare_judgment(output, _context())["pass"] is True


def test_broken_fixture_reports_each_problem():
    problems = check_judgments(_fixture("smoke_compare_broken"), CARDS, FACTS, SOURCE)
    text = " ".join(problems)
    assert "허용값 아님 GOOD" in text
    assert "CONVEYED인데 spans 없음" in text
    assert "원문에 없는 인용" in text
    assert "V-01/C2" in text


def test_distorted_fact_needs_evidence():
    judgments = _fixture("smoke_compare_valid")
    for j in judgments:
        if j.get("fact_id") == "F2":
            j["evidence"] = ""
    problems = check_judgments(judgments, CARDS, FACTS, SOURCE)
    assert any("DISTORTED인데 evidence 없음" in p for p in problems)


def test_quote_check_ignores_whitespace_only():
    judgments = _fixture("smoke_compare_valid")
    for j in judgments:
        if j.get("fact_id") == "F1":
            j["spans"][0]["source_quote"] = "아산시는  전기차 196대를\n지원하며"
    assert check_judgments(judgments, CARDS, FACTS, SOURCE) == []


def test_string_spans_are_reported_not_crashed():
    judgments = _fixture("smoke_compare_valid")
    judgments[0]["spans"] = ["제목 문구"]
    problems = check_judgments(judgments, CARDS, FACTS, SOURCE)
    assert any("spans는 객체 목록이어야 함" in p for p in problems)


def test_agreement_counts_only_human_judged_items():
    ai = [
        {"question_id": "C-01", "card_id": "C2", "verdict": "NOT_MET"},
        {"question_id": "S-02", "verdict": "MET"},
        {"question_id": "V-01", "card_id": "C1", "verdict": "MET"},
    ]
    human = [
        {"question_id": "C-01", "card_id": "C2", "verdict": "NOT_MET"},
        {"question_id": "S-02", "verdict": "NOT_MET"},
    ]
    same, total, diff = agreement(ai, human)
    assert (same, total) == (1, 2)
    assert "S-02" in diff[0]


def test_human_agreement_skips_when_no_human_labels():
    result = human_agreement(json.dumps({"judgments": []}), _context())
    assert result["pass"] is True and "사람 판정 없음" in result["reason"]


def test_replay_provider_returns_fixture():
    context = _context(case_id="smoke_compare_valid", service="CardSync")
    result = call_api("", {"config": {"mode": "replay"}}, context)
    assert json.loads(result["output"])["judgments"][0]["question_id"] == "V-01"
    assert result["cost"] == 0


def test_instructions_list_every_ai_question():
    text = build_instructions(load_questions())
    for q in ai_questions():
        assert q["id"] in text
    assert "D-07" not in text


def test_export_keeps_factuality_and_completeness_separate():
    results = {
        "results": {
            "results": [
                {
                    "vars": {"case_id": "a01", "article_no": 1, "service": "CardSync"},
                    "response": {
                        "output": json.dumps({"judgments": _fixture("smoke_compare_valid")})
                    },
                }
            ]
        }
    }
    records = to_records(results)
    assert all(r[2] == "AI" for r in records)
    c01 = [r for r in records if r[3] == "C-01" and r[5] == "미충족"]
    assert c01 and c01[0][6] == 1 and "870만원" in c01[0][7]
    summary = summarize(records)["CardSync"]
    assert summary["사실성_틀린문구수"] == 1
    assert (summary["완전성_전달"], summary["완전성_왜곡"], summary["완전성_누락"]) == (1, 1, 0)
    assert summary["완전성_전달률"] == 0.5


def test_load_facts_passes_only_fact_fields(tmp_path: Path):
    path = tmp_path / "facts.json"
    path.write_text(
        json.dumps(
            {
                "case": "a01",
                "facts": [
                    {
                        "id": "F1",
                        "type": "시점",
                        "text": "10월 29일부터 시행한다",
                        "lines": [1],
                        "evidence": "29일부터",
                    },
                    {
                        "id": "F2",
                        "text": "확대할 방침이다",
                        "wording": "미확정",
                        "hedge": "방침이다",
                    },
                ],
                "excluded": [{"lines": [3], "what": "예산 105억 원", "why": "세부 예산"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert load_facts(path) == [
        {"id": "F1", "text": "10월 29일부터 시행한다"},
        {"id": "F2", "text": "확대할 방침이다", "wording": "미확정", "hedge": "방침이다"},
    ]


def test_load_facts_accepts_plain_list(tmp_path: Path):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps([{"id": "F1", "text": "가"}]), encoding="utf-8")
    assert load_facts(path) == [{"id": "F1", "text": "가"}]


def test_completeness_question_states_wording_rules():
    c02 = next(q for q in load_questions()["questions"] if q["id"] == "C-02")
    assert "미확정" in c02["question"] and "요청" in c02["question"]
    assert "절대 날짜" in c02["question"]
