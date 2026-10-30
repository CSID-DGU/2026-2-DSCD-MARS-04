import json
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai.analysis import agent
from ai.analysis.agent import analyze, estimate_cost
from ai.analysis.grouper import GroupingResult, check_grouping, group_sentences, order_groups
from ai.analysis.summarizer import SummaryResult, find_missing_numbers, summarize_groups
from data_pipeline.schemas.group import GroupAnalysis

SENTENCES = [
    {"sentence_id": "S1", "text": "군은 14일 교육을 했다."},
    {"sentence_id": "S2", "text": "주민 1,200명이 참석했다."},
    {"sentence_id": "S3", "text": "감시원 58명을 배치했다."},
    {"sentence_id": "S4", "text": "행사는 무사히 끝났다."},
]
IDS = [s["sentence_id"] for s in SENTENCES]
GOOD_GROUPS = [
    {"group_id": "G1", "sentence_ids": ["S1", "S2"]},
    {"group_id": "G2", "sentence_ids": ["S3"]},
    {"group_id": "G3", "sentence_ids": ["S4"]},
]
SOURCE_TEXT = " ".join(s["text"] for s in SENTENCES)


def keep_all(group: dict) -> str:
    return " ".join(s["text"] for s in group["sentences"])


def drop_numbers(group: dict) -> str:
    return re.sub(r"\d[\d,]*", "", keep_all(group))


def fake_client(groupings=None, summarize=keep_all):
    """그룹화는 groupings를 순서대로 돌려주고, 요약은 summarize(그룹)로 만든다."""
    groupings = list(groupings or [GOOD_GROUPS])

    def parse(**kwargs):
        payload = json.loads(kwargs["input"][1]["content"])
        if kwargs["text_format"] is GroupingResult:
            groups = groupings.pop(0) if len(groupings) > 1 else groupings[0]
            parsed = GroupingResult.model_validate({"groups": groups})
        else:
            summaries = [
                {"group_id": g["group_id"], "summary": summarize(g)} for g in payload["groups"]
            ]
            parsed = SummaryResult.model_validate({"summaries": summaries})
        return SimpleNamespace(
            output_parsed=parsed,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            model="gpt-4.1-mini-2025-04-14",
        )

    client = Mock()
    client.responses.parse.side_effect = parse
    return client


def requested(client, text_format) -> list[dict]:
    """해당 단계에서 API에 보낸 입력들."""
    return [
        json.loads(call.kwargs["input"][1]["content"])
        for call in client.responses.parse.call_args_list
        if call.kwargs["text_format"] is text_format
    ]


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUPING_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("SUMMARY_MODEL", "gpt-6-luna")
    monkeypatch.setenv("ANALYSIS_LOG_PATH", str(tmp_path / "analysis.jsonl"))
    monkeypatch.setattr(agent, "split_sentences", lambda text: SENTENCES if text else [])


# ---------- 그룹화 ----------


@pytest.mark.parametrize(
    "groups,message",
    [
        ([{"group_id": "G1", "sentence_ids": ["S1", "S2", "S3"]}], "들어가지 않은"),
        (GOOD_GROUPS + [{"group_id": "G4", "sentence_ids": ["S4"]}], "두 번 이상"),
        (GOOD_GROUPS + [{"group_id": "G4", "sentence_ids": ["S9"]}], "없는 문장 ID"),
        (
            [
                {"group_id": "G1", "sentence_ids": ["S1", "S3"]},
                {"group_id": "G2", "sentence_ids": ["S2", "S4"]},
            ],
            "붙어 있지 않은",
        ),
        (GOOD_GROUPS + [{"group_id": "G4", "sentence_ids": []}], "빈 그룹"),
    ],
    ids=["missing", "duplicate", "unknown", "not_contiguous", "empty"],
)
def test_check_grouping_catches_errors(groups, message):
    errors = check_grouping(IDS, groups)
    assert any(message in error for error in errors)


def test_check_grouping_passes_good_groups():
    assert check_grouping(IDS, GOOD_GROUPS) == []


def test_order_groups_sorts_and_renumbers():
    shuffled = [
        {"group_id": "A", "sentence_ids": ["S4"]},
        {"group_id": "B", "sentence_ids": ["S2", "S1"]},
        {"group_id": "C", "sentence_ids": ["S3"]},
    ]
    assert order_groups(shuffled, IDS) == GOOD_GROUPS


def test_grouping_retry_recovers_and_records_each_call():
    first = [{"group_id": "G1", "sentence_ids": ["S1", "S2", "S3"]}]
    client = fake_client(groupings=[first, GOOD_GROUPS])
    result = group_sentences(SENTENCES, client=client)

    assert result["valid"] and not result["first_try_valid"]
    assert result["attempts"] == 2
    assert [call["attempt"] for call in result["calls"]] == [1, 2]
    assert result["calls"][0]["errors"] and result["calls"][1]["errors"] == []
    assert "previous_errors" in requested(client, GroupingResult)[1]
    assert result["input_tokens"] == 2000


def test_grouping_stops_after_max_retries():
    bad = [{"group_id": "G1", "sentence_ids": ["S1"]}]
    client = fake_client(groupings=[bad])
    result = group_sentences(SENTENCES, client=client, max_retries=1)

    assert not result["valid"]
    assert result["attempts"] == 2
    assert client.responses.parse.call_count == 2


# ---------- 요약 ----------


def test_find_missing_numbers_treats_commas_as_same():
    assert find_missing_numbers("주민 1,200명, 58명", "주민 1200명, 58명") == []
    assert find_missing_numbers("14일 58명", "14일") == ["58"]


def test_summary_passes_without_retry():
    client = fake_client()
    result = summarize_groups(SENTENCES, GOOD_GROUPS, client=client)

    assert result["attempts"] == 1
    assert result["retried_group_ids"] == [] and result["fallback_group_ids"] == []
    assert len(result["calls"]) == 1


def test_summary_retries_only_failed_group_and_recovers():
    def g2_fixed_on_retry(group):
        if group["group_id"] == "G2" and "previous_error" not in group:
            return drop_numbers(group)
        return keep_all(group)

    client = fake_client(summarize=g2_fixed_on_retry)
    result = summarize_groups(SENTENCES, GOOD_GROUPS, client=client)

    assert result["retried_group_ids"] == ["G2"]
    assert result["fallback_group_ids"] == []
    assert result["calls"][1]["group_ids"] == ["G2"]
    retry_input = requested(client, SummaryResult)[1]
    assert [g["group_id"] for g in retry_input["groups"]] == ["G2"]
    assert "58" in retry_input["groups"][0]["previous_error"]


def test_summary_falls_back_to_source_when_retry_fails():
    client = fake_client(summarize=drop_numbers)
    result = summarize_groups(SENTENCES, GOOD_GROUPS, client=client)

    assert result["attempts"] == 2
    assert set(result["fallback_group_ids"]) == {"G1", "G2"}
    summaries = {g["group_id"]: g["summary"] for g in result["groups"]}
    assert summaries["G1"] == "군은 14일 교육을 했다. 주민 1,200명이 참석했다."
    assert summaries["G2"] == "감시원 58명을 배치했다."
    assert summaries["G3"] == "행사는 무사히 끝났다."


def test_empty_summary_is_retried():
    def empty_first(group):
        return keep_all(group) if "previous_error" in group else ""

    result = summarize_groups(SENTENCES, GOOD_GROUPS, client=fake_client(summarize=empty_first))
    assert len(result["retried_group_ids"]) == 3
    assert result["fallback_group_ids"] == []


# ---------- 분석 에이전트: 출력 ----------


def test_analyze_output_matches_group_analysis():
    result = analyze("news_001", SOURCE_TEXT, client=fake_client())

    assert set(result) == {"document_id", "groups"}
    assert result["document_id"] == "news_001"
    for group in result["groups"]:
        assert set(group) == {"group_id", "sentence_ids", "summary"}
        GroupAnalysis.model_validate(group)
    used = [i for g in result["groups"] for i in g["sentence_ids"]]
    assert used == IDS


# ---------- 분석 에이전트: 로그 ----------


def read_log(tmp_path) -> list[dict]:
    path = tmp_path / "analysis.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_success_log_appends_and_records_calls(tmp_path):
    client = fake_client(summarize=drop_numbers)
    for _ in range(2):
        analyze("news_001", SOURCE_TEXT, client=client)

    records = read_log(tmp_path)
    assert len(records) == 2
    assert records[0]["run_id"] != records[1]["run_id"]

    record = records[0]
    assert record["status"] == "success"
    assert record["stage"] == "output"
    assert record["sentence_count"] == 4
    assert len(record["source_sha256"]) == 64
    assert record["grouping"]["response_model"] == "gpt-4.1-mini-2025-04-14"
    assert record["grouping"]["max_retries"] == 1
    assert len(record["grouping"]["prompt_sha256"]) == 64
    assert record["summary"]["attempts"] == 2
    assert [c["attempt"] for c in record["summary"]["calls"]] == [1, 2]
    assert record["summary"]["calls"][1]["requested_group_ids"] == ["G1", "G2"]
    assert record["estimated_cost_usd"] == pytest.approx(
        record["grouping"]["estimated_cost_usd"] + record["summary"]["estimated_cost_usd"]
    )
    assert record["result"]["document_id"] == "news_001"


def test_log_does_not_contain_source_text(tmp_path):
    def shorten(group):
        return keep_all(group).replace("교육을 했다", "교육")

    analyze("news_001", SOURCE_TEXT, client=fake_client(summarize=shorten))
    text = (tmp_path / "analysis.jsonl").read_text(encoding="utf-8")
    assert "교육을 했다" not in text


@pytest.mark.parametrize("failure", ["split", "grouping", "api"])
def test_failure_log_and_original_exception(tmp_path, failure):
    client = fake_client()
    text = SOURCE_TEXT
    if failure == "split":
        text = ""
    elif failure == "grouping":
        client = fake_client(groupings=[[{"group_id": "G1", "sentence_ids": ["S1"]}]])
    else:
        client.responses.parse.side_effect = RuntimeError("secret-input-and-key")

    with pytest.raises((ValueError, RuntimeError)):
        analyze("news_001", text, client=client)

    record = read_log(tmp_path)[0]
    assert record["status"] == "failed"
    expected_stage = {"split": "split", "grouping": "grouping", "api": "grouping"}[failure]
    assert record["error"]["stage"] == expected_stage
    assert "result" not in record
    assert "secret-input-and-key" not in (tmp_path / "analysis.jsonl").read_text(encoding="utf-8")
    if failure == "grouping":
        assert record["grouping"]["valid"] is False
        assert record["grouping"]["attempts"] == 2


def test_log_write_failure_does_not_replace_result(tmp_path, capsys):
    result = analyze("news_001", SOURCE_TEXT, client=fake_client(), log_path=tmp_path)
    assert result["document_id"] == "news_001"
    assert "로그 파일" in capsys.readouterr().err


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4.1-mini-2025-04-14", 0.56),
        ("gpt-4.1-mini", 0.56),
        ("gpt-6-luna", 0.15),
        ("o3", None),
        (None, None),
    ],
)
def test_estimate_cost(model, expected):
    assert estimate_cost(model, 1_000_000, 100_000) == expected
