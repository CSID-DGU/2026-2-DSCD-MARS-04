"""요청 ID와 JSON 로그 테스트. 원문·키가 로그에 남지 않는지도 확인한다."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from test_api import TEXT, FakePipeline

from backend.core.logging import JsonFormatter, logger
from backend.core.store import Store
from backend.main import BASE, create_app

SECRET_LIKE = "sk-test-should-never-appear"


@pytest.fixture
def client_and_logs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET_LIKE)
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(json.loads(JsonFormatter().format(record)))

    handler = Capture()
    logger.addHandler(handler)
    client = TestClient(create_app(store=Store(":memory:"), pipeline=FakePipeline()))
    yield client, records
    logger.removeHandler(handler)


def requests_of(records):
    return [r for r in records if r["event"] == "http_request"]


def test_request_id_generated_and_returned(client_and_logs):
    client, records = client_and_logs
    res = client.get(f"{BASE}/health")
    rid = res.headers["X-Request-ID"]
    assert len(rid) == 32
    (entry,) = requests_of(records)
    assert entry == {
        "ts": entry["ts"],
        "level": "INFO",
        "event": "http_request",
        "request_id": rid,
        "method": "GET",
        "route": "/api/v1/health",
        "status": 200,
        "duration_ms": entry["duration_ms"],
    }


def test_client_request_id_reused_only_when_valid(client_and_logs):
    client, records = client_and_logs
    good = client.get(f"{BASE}/health", headers={"X-Request-ID": "demo-run-0001"})
    assert good.headers["X-Request-ID"] == "demo-run-0001"
    bad = client.get(f"{BASE}/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert bad.headers["X-Request-ID"] != "bad id\nwith newline"
    assert len(bad.headers["X-Request-ID"]) == 32


def test_route_template_and_error_status(client_and_logs):
    client, records = client_and_logs
    res = client.get(f"{BASE}/documents/doc_missing")
    assert res.status_code == 404 and "X-Request-ID" in res.headers
    client.get("/.env.local")
    routes = [(r["route"], r["status"]) for r in requests_of(records)]
    assert routes == [("/api/v1/documents/{document_id}", 404), ("<unmatched>", 404)]


def test_job_stages_and_request_id(client_and_logs):
    client, records = client_and_logs
    res = client.post(f"{BASE}/documents", json={"text": TEXT})
    rid = res.headers["X-Request-ID"]
    job = client.get(f"{BASE}/jobs/{res.json()['data']['job_id']}").json()["data"]
    assert job["request_id"] == rid
    assert [s["name"] for s in job["stages"]] == ["start", "analysis", "titles"]
    assert all(s["status"] == "ok" and s["duration_ms"] >= 0 for s in job["stages"])
    stage_logs = [r for r in records if r["event"] == "job_stage"]
    assert [r["stage"] for r in stage_logs] == ["start", "analysis", "titles"]
    assert all(r["request_id"] == rid for r in stage_logs)
    (finished,) = [r for r in records if r["event"] == "job_finished"]
    assert finished["status"] == "succeeded" and finished["request_id"] == rid


def test_failed_stage_logged_without_message(client_and_logs, monkeypatch):
    client, records = client_and_logs
    client.app.state.pipeline = FakePipeline(fail_stage="analysis")
    res = client.post(f"{BASE}/documents", json={"text": TEXT})
    job = client.get(f"{BASE}/jobs/{res.json()['data']['job_id']}").json()["data"]
    assert job["stages"][-1] == {
        "name": "analysis",
        "duration_ms": job["stages"][-1]["duration_ms"],
        "status": "failed",
    }
    (finished,) = [r for r in records if r["event"] == "job_finished"]
    assert finished["status"] == "failed" and finished["error_type"] == "RuntimeError"


def test_llm_tokens_recorded_per_stage(client_and_logs):
    from types import SimpleNamespace

    from openai.resources.responses import Responses

    from backend.core import llm_usage

    assert hasattr(Responses.parse, "__wrapped__")  # SDK 감싸기가 설치됨
    fake_parse = llm_usage._wrap(
        lambda self: SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20))
    )

    class TokenPipeline(FakePipeline):
        def analyze(self, document_id, text):
            fake_parse(None)
            fake_parse(None)
            return super().analyze(document_id, text)

    client, records = client_and_logs
    client.app.state.pipeline = TokenPipeline()
    res = client.post(f"{BASE}/documents", json={"text": TEXT})
    job = client.get(f"{BASE}/jobs/{res.json()['data']['job_id']}").json()["data"]
    analysis, titles = job["stages"][1], job["stages"][2]
    assert (analysis["llm_calls"], analysis["input_tokens"], analysis["output_tokens"]) == (
        2,
        200,
        40,
    )
    assert "llm_calls" not in titles  # LLM을 안 부른 단계에는 붙지 않는다
    (finished,) = [r for r in records if r["event"] == "job_finished"]
    assert (finished["input_tokens"], finished["output_tokens"]) == (200, 40)


def test_logs_never_contain_source_text_or_key(client_and_logs):
    client, records = client_and_logs
    client.post(f"{BASE}/documents?token=abc", json={"text": TEXT})
    client.app.state.pipeline = FakePipeline(fail_stage="analysis")
    client.post(f"{BASE}/documents", json={"text": TEXT})
    dumped = json.dumps(records, ensure_ascii=False)
    assert SECRET_LIKE not in dumped
    assert "secret text should not leak" not in dumped  # FakePipeline 예외 메시지
    assert "token=abc" not in dumped
    for sentence in TEXT.split(". ")[:3]:
        assert sentence[:20] not in dumped
