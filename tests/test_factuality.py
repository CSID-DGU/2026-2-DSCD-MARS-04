import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ai.verification.factuality.checker import JudgmentResult, check_factuality


def fake_client(supported=True):
    def parse(**kwargs):
        payload = json.loads(kwargs["input"][1]["content"])
        judgments = [
            {
                "item_id": item["item_id"],
                "supported": supported,
                "problems": [] if supported else [{"quote": item["text"], "reason": "다름"}],
            }
            for item in payload["items"]
        ]
        return SimpleNamespace(
            output_parsed=JudgmentResult.model_validate({"judgments": judgments}),
            model="gpt-6-luna-test",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    return SimpleNamespace(responses=SimpleNamespace(parse=Mock(side_effect=parse)))


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    monkeypatch.setenv("FACTUALITY_MODEL", "gpt-6-luna")


def test_number_rule_fails_without_llm_call():
    client = fake_client()
    item = {"item_id": "I1", "source": "최대 5개 지역", "text": "7개 지역"}
    result = check_factuality([item], client=client)
    assert result["results"][0]["status"] == "FAIL"
    assert result["results"][0]["by"] == "rule"
    client.responses.parse.assert_not_called()


def test_llm_judgment_maps_to_status():
    item = {"item_id": "I1", "source": "최대 5개 지역", "text": "5개 지역"}
    passed = check_factuality([item], client=fake_client(supported=True))["results"][0]
    failed = check_factuality([item], client=fake_client(supported=False))["results"][0]
    assert (passed["status"], passed["by"]) == ("PASS", "llm")
    assert failed["status"] == "FAIL"
    assert failed["problems"][0]["quote"] == "5개 지역"


def test_reasoning_turned_off_for_gpt6():
    client = fake_client()
    check_factuality([{"item_id": "I1", "source": "가", "text": "가"}], client=client)
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["temperature"] == 0


def test_by_sentence_fails_if_any_sentence_fails():
    client = fake_client()
    item = {
        "item_id": "G1",
        "source": "정부는 최대 5개 지역에 지원한다. 신청은 3월까지다.",
        "text": "정부는 5개 지역에 지원한다. 신청은 7월까지다.",
    }
    result = check_factuality([item], by_sentence=True, client=client)["results"][0]
    assert result["status"] == "FAIL"
    assert [s["status"] for s in result["sentences"]] == ["PASS", "FAIL"]  # 7월은 숫자 규칙
    sent = json.loads(client.responses.parse.call_args.kwargs["input"][1]["content"])["items"]
    assert [i["item_id"] for i in sent] == ["G1#1"]  # 숫자 규칙에 걸린 문장은 LLM에 안 보냄


def test_by_sentence_passes_previous_text():
    client = fake_client()
    item = {"item_id": "G1", "source": "가. 나.", "text": "가는 크다. 이는 작다."}
    check_factuality([item], by_sentence=True, client=client)
    sent = json.loads(client.responses.parse.call_args.kwargs["input"][1]["content"])["items"]
    assert "previous_text" not in sent[0]
    assert sent[1]["previous_text"] == "가는 크다."
