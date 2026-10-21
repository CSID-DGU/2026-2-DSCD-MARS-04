import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from ai.generation.group_titles import ROOT, GroupTitlesOutput, generate_group_titles


@pytest.fixture
def sample():
    return json.loads((ROOT / "data/samples/group_analysis_sample.json").read_text())


def fake_client(sample):
    result = GroupTitlesOutput.model_validate(
        {
            "document_id": sample["document_id"],
            "group_presentations": [
                {
                    "group_id": g["group_id"],
                    "topic": "테스트 주제",
                    "headline": "테스트 제목",
                }
                for g in sample["groups"]
            ],
        }
    )
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        status="completed",
        output=[],
        output_parsed=result,
    )
    return client


def test_sample_and_model_switch(sample, monkeypatch):
    original = deepcopy(sample)
    monkeypatch.setenv("GENERATION_MODEL", "gpt-5-mini")
    client = fake_client(sample)
    result = generate_group_titles(sample, client=client)
    assert len(result.group_presentations) == 5
    assert sample == original
    assert client.responses.parse.call_args.kwargs["model"] == "gpt-5-mini"
    generate_group_titles(sample, client=client, model="gpt-4.1-mini")
    assert client.responses.parse.call_args.kwargs["model"] == "gpt-4.1-mini"


@pytest.mark.parametrize(
    "change",
    ["reverse", "missing", "extra", "duplicate", "unknown", "document", "blank"],
)
def test_invalid_output(sample, change):
    client = fake_client(sample)
    result = client.responses.parse.return_value.output_parsed
    groups = result.group_presentations
    if change == "reverse":
        groups.reverse()
    elif change == "missing":
        groups.pop()
    elif change == "extra":
        groups.append(groups[0])
    elif change == "duplicate":
        groups[1].group_id = groups[0].group_id
    elif change == "unknown":
        groups[0].group_id = "unknown"
    elif change == "document":
        result.document_id = "other"
    else:
        groups[0].headline = " "
    with pytest.raises(ValueError):
        generate_group_titles(sample, client=client)


@pytest.mark.parametrize("change", ["duplicate", "empty", "schema"])
def test_invalid_input_before_api(sample, change):
    client = fake_client(sample)
    if change == "duplicate":
        sample["groups"][1]["group_id"] = "G1"
    elif change == "empty":
        sample["groups"] = []
    else:
        del sample["groups"][0]["summary"]
    with pytest.raises((ValueError, ValidationError)):
        generate_group_titles(sample, client=client)
    client.responses.parse.assert_not_called()


@pytest.mark.parametrize(
    "status,parsed,output",
    [
        ("incomplete", None, []),
        ("completed", None, []),
        (
            "completed",
            None,
            [SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="거부")])],
        ),
    ],
)
def test_failed_response(sample, status, parsed, output):
    client = fake_client(sample)
    client.responses.parse.return_value = SimpleNamespace(
        status=status,
        output_parsed=parsed,
        output=output,
    )
    with pytest.raises(RuntimeError):
        generate_group_titles(sample, client=client)


@pytest.fixture(autouse=True)
def isolate_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("GENERATION_LOG_PATH", str(tmp_path / "runs.jsonl"))


def test_success_log_appends_and_preserves_usage(sample, tmp_path):
    client = fake_client(sample)
    response = client.responses.parse.return_value
    response.id = "resp_test"
    response.model = "gpt-4.1-mini-test"
    response.usage = SimpleNamespace(
        model_dump=lambda **kwargs: {
            "input_tokens": 120,
            "output_tokens": 80,
            "total_tokens": 200,
            "output_tokens_details": {"reasoning_tokens": 0},
        }
    )
    path = tmp_path / "nested" / "runs.jsonl"
    for _ in range(2):
        generate_group_titles(sample, client=client, log_path=path)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 2
    assert records[0]["run_id"] != records[1]["run_id"]
    record = records[0]
    assert record["status"] == "success"
    assert record["document_id"] == "news_001"
    assert record["group_count"] == 5
    assert record["usage"]["total_tokens"] == 200
    assert record["response_id"] == "resp_test"
    assert len(record["prompt_sha256"]) == 64
    assert record["elapsed_seconds"] >= 0
    assert len(record["result"]["group_presentations"]) == 5
    assert sample["groups"][0]["summary"] not in path.read_text()


@pytest.mark.parametrize("failure", ["input", "api", "output"])
def test_failure_log_and_original_exception(sample, tmp_path, failure):
    client = fake_client(sample)
    if failure == "input":
        del sample["groups"][0]["summary"]
    elif failure == "api":
        client.responses.parse.side_effect = RuntimeError("secret-input-and-key")
    else:
        client.responses.parse.return_value.output_parsed.document_id = "wrong"
    with pytest.raises((ValueError, RuntimeError)):
        generate_group_titles(sample, client=client)
    text = (tmp_path / "runs.jsonl").read_text()
    record = json.loads(text)
    assert record["status"] == "failed"
    assert (
        record["error"]["stage"]
        == {
            "input": "input_validation",
            "api": "api_call",
            "output": "output_validation",
        }[failure]
    )
    assert "secret-input-and-key" not in text
    assert "result" not in record


def test_log_write_failure_does_not_replace_result(sample, tmp_path, capsys):
    result = generate_group_titles(sample, client=fake_client(sample), log_path=tmp_path)
    assert result.document_id == "news_001"
    assert "로그 파일" in capsys.readouterr().err
