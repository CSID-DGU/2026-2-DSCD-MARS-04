"""백엔드 API 테스트. LLM은 가짜 파이프라인으로 대체해 API 키 없이 돈다."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.core.store import Store
from backend.main import BASE, create_app
from backend.services.pipeline import RepoPipeline

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "savings.json").read_text("utf-8"))
TEXT = " ".join(s["text"] for s in FIXTURE["sentences"])


class FakePipeline:
    """레포 함수와 같은 모양의 입출력을 돌려준다. 문장 분리는 레포 함수를 그대로 쓴다."""

    def __init__(self, fail_stage=None):
        self.fail_stage = fail_stage
        self.check_items = []

    def split(self, text):
        return RepoPipeline().split(text)

    def analyze(self, document_id, text):
        if self.fail_stage == "analysis":
            raise RuntimeError("secret text should not leak")
        return [
            {"group_id": "G1", "sentence_ids": ["S1", "S3", "S4"], "summary": "사업 개요"},
            {"group_id": "G2", "sentence_ids": ["S2"], "summary": "모집 일정"},
            {"group_id": "G3", "sentence_ids": ["S5", "S6"], "summary": "가입 요건"},
        ]

    def titles(self, document_id, groups):
        return [{**g, "topic": f"주제 {g['group_id']}", "headline": "미리보기"} for g in groups]

    def generate(self, document_id, groups):
        cards = []
        for g in groups:
            cards.append(
                {
                    "group_id": g["group_id"],
                    "layout_id": "body",
                    "sids": g["sentence_ids"],
                    "title": f"{g['group_id']} 카드",
                    "body": "매월 10만 원을 저축합니다.",
                    "image_query": "savings",
                }
            )
        return cards

    def check_cards(self, document_id, groups, cards):
        """수연 검사기 모양: 카드별 필드 판정 + 완전성 + 피드백. 999가 있으면 왜곡, 수정안 제시."""
        self.card_inputs = (groups, cards)
        by_card = {}
        for c in cards:
            if c["group_id"] is None:
                by_card[c["card_id"]] = {"status": "NOT_CHECKED", "fields": []}
                continue
            bad = "999" in (c.get("body") or "")
            by_card[c["card_id"]] = {
                "status": "POSSIBLE_DISTORTION" if bad else "SUPPORTED",
                "fields": [
                    {
                        "unit_id": f"{c['card_id']}:body",
                        "card_id": c["card_id"],
                        "group_id": c["group_id"],
                        "field_path": "body",
                        "card_text": c.get("body") or "",
                        "status": "POSSIBLE_DISTORTION" if bad else "SUPPORTED",
                        "evidence": "매월 10만 원",
                        "reason": "금액이 요약과 다릅니다." if bad else "",
                        "error_type": "수치 변경" if bad else None,
                        "suggested_text": "매월 10만 원을 저축합니다." if bad else None,
                    }
                ],
            }
        return {
            "status": "ISSUES_FOUND",
            "model": "fake-4.1-mini",
            "cards": by_card,
            "completeness": [
                {
                    "fact_id": f"{g['group_id']}:summary",
                    "group_id": g["group_id"],
                    "status": "COVERED",
                    "matched_card_ids": [
                        c["card_id"] for c in cards if c["group_id"] == g["group_id"]
                    ],
                    "reason": "",
                    "missing_elements": [],
                }
                for g in groups
            ],
            "feedback": [],
            "unchecked": [],
        }

    def check(self, items):
        self.check_items.extend(items)
        return [
            {
                "item_id": i["item_id"],
                "status": "FAIL" if "999" in i["text"] else "PASS",
                "by": "rule" if "999" in i["text"] else "llm",
                "problems": [],
            }
            for i in items
        ]


@pytest.fixture
def make_client():
    def _make(pipeline=None):
        pipeline = pipeline or FakePipeline()
        app = create_app(store=Store(":memory:"), pipeline=pipeline)
        return TestClient(app), pipeline

    return _make


def analyzed(client):
    res = client.post(f"{BASE}/documents", json={"text": TEXT, "title": FIXTURE["title"]})
    assert res.status_code == 202
    data = res.json()["data"]
    job = client.get(f"{BASE}/jobs/{data['job_id']}").json()["data"]
    assert job["status"] == "succeeded", job
    return data["document_id"]


def generated(client, ids=("G1", "G3")):
    doc_id = analyzed(client)
    assert (
        client.put(
            f"{BASE}/documents/{doc_id}/selection", json={"required_group_ids": list(ids)}
        ).status_code
        == 200
    )
    res = client.post(f"{BASE}/documents/{doc_id}/cards")
    assert res.status_code == 202
    job = client.get(f"{BASE}/jobs/{res.json()['data']['job_id']}").json()["data"]
    assert job["status"] == "succeeded", job
    return doc_id


def test_health_and_layouts(make_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client, _ = make_client()
    body = client.get(f"{BASE}/health").json()
    assert body == {
        "code": 200,
        "message": "서버가 정상입니다.",
        "data": {"status": "ok", "openai_key_configured": False},
    }
    layouts = client.get(f"{BASE}/layouts").json()["data"]
    assert layouts["layouts"]["body"]["fields"]["body"]["max_chars"] == 110


def test_document_analysis_and_selection(make_client):
    client, _ = make_client()
    doc_id = analyzed(client)
    doc = client.get(f"{BASE}/documents/{doc_id}").json()["data"]
    assert [s["sentence_id"] for s in doc["sentences"]] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert doc["groups"][0] == {
        "group_id": "G1",
        "sentence_ids": ["S1", "S3", "S4"],
        "summary": "사업 개요",
        "topic": "주제 G1",
        "headline": "미리보기",
    }
    res = client.put(
        f"{BASE}/documents/{doc_id}/selection", json={"required_group_ids": ["G3", "G1"]}
    )
    assert res.json()["data"] == {
        "document_id": doc_id,
        "required_group_ids": ["G1", "G3"],
        "cards_outdated": False,
    }


@pytest.mark.parametrize(
    ("payload", "code", "message"),
    [
        ({"text": "   "}, 400, "원문이 비어 있습니다."),
        ({"text": "가" * 20001}, 413, "원문이 너무 깁니다. 20,000자 이하로 입력해 주세요."),
        ({}, 400, None),
    ],
)
def test_document_validation(make_client, payload, code, message):
    client, _ = make_client()
    res = client.post(f"{BASE}/documents", json=payload)
    assert res.status_code == code
    assert res.json()["code"] == code and "data" not in res.json()
    if message:
        assert res.json()["message"] == message


def test_selection_errors(make_client):
    client, _ = make_client()
    doc_id = analyzed(client)
    url = f"{BASE}/documents/{doc_id}/selection"
    assert (
        client.put(url, json={"required_group_ids": []}).json()["message"]
        == "선택된 그룹이 없습니다."
    )
    assert (
        client.put(url, json={"required_group_ids": ["G9"]}).json()["message"]
        == "존재하지 않는 그룹 ID: ['G9']"
    )
    assert (
        client.put(
            f"{BASE}/documents/nope/selection", json={"required_group_ids": ["G1"]}
        ).status_code
        == 404
    )


def test_analysis_failure_hides_message(make_client):
    client, _ = make_client(FakePipeline(fail_stage="analysis"))
    res = client.post(f"{BASE}/documents", json={"text": TEXT}).json()["data"]
    job = client.get(f"{BASE}/jobs/{res['job_id']}").json()["data"]
    assert job["status"] == "failed"
    assert job["error"] == {"type": "RuntimeError", "stage": "analysis"}
    assert "secret" not in json.dumps(job)
    assert client.get(f"{BASE}/documents/{res['document_id']}").status_code == 409


def test_cards_generated_with_cover_and_closing(make_client):
    client, _ = make_client()
    doc_id = generated(client)
    cards = client.get(f"{BASE}/documents/{doc_id}/cards").json()["data"]["cards"]
    assert [c["layout_id"] for c in cards] == ["cover", "body", "body", "closing"]
    assert [c["card_id"] for c in cards] == ["C1", "C2", "C3", "C4"]
    assert [c["generated_by"] for c in cards] == ["template", "llm", "llm", "template"]
    assert cards[0]["group_id"] is None and cards[1]["group_id"] == "G1"
    assert all(
        c["version"] == 1 and c["status"] == "unchecked" and c["check"] is None for c in cards
    )
    again = client.post(f"{BASE}/documents/{doc_id}/cards")
    assert again.status_code == 409


def test_edit_check_and_invalidation(make_client):
    client, pipeline = make_client()
    doc_id = generated(client)
    res = client.post(f"{BASE}/documents/{doc_id}/checks", json={"stage": "summary"})
    assert res.status_code == 202
    assert res.json()["data"]["card_ids"] == ["C2", "C3"]  # sids 없는 표지·마무리는 검사하지 않는다
    source_c2 = next(i for i in pipeline.check_items if i["item_id"] == "C2")["source"]
    stored = client.get(f"{BASE}/documents/{doc_id}").json()["data"]["sentences"]
    assert source_c2 == " ".join(stored[i]["text"] for i in (0, 2, 3))  # S1 S3 S4, 원문 순서

    card = next(
        c
        for c in client.get(f"{BASE}/documents/{doc_id}/cards").json()["data"]["cards"]
        if c["card_id"] == "C2"
    )
    assert card["status"] == "ok"
    assert (
        card["check"]["card_version"] == 1
        and card["check"]["checker"] == "summary-consistency@8c9242c"
    )

    url = f"{BASE}/documents/{doc_id}/cards/C2"
    edited = client.patch(
        url, json={"expected_version": 1, "body": "매월 999만 원을 줍니다."}
    ).json()["data"]["card"]
    assert edited["version"] == 2 and edited["status"] == "pending" and edited["check"] is None

    record = client.get(f"{BASE}/documents/{doc_id}/record").json()["data"]
    rec_c2 = next(c for c in record["cards"] if c["card_id"] == "C2")
    assert rec_c2["check"] is None and record["unverified_card_count"] == 3

    client.post(f"{BASE}/documents/{doc_id}/checks", json={"stage": "summary"})
    card = next(
        c
        for c in client.get(f"{BASE}/documents/{doc_id}/cards").json()["data"]["cards"]
        if c["card_id"] == "C2"
    )
    assert card["status"] == "bad" and card["check"]["card_version"] == 2

    stale = client.patch(url, json={"expected_version": 1, "title": "새 제목"})
    assert stale.status_code == 409


def test_patch_validation(make_client):
    client, _ = make_client()
    doc_id = generated(client)
    url = f"{BASE}/documents/{doc_id}/cards/C2"
    assert (
        client.patch(url, json={"expected_version": 1, "title": " "}).json()["message"]
        == "카드 제목은 비어 있을 수 없습니다."
    )
    assert client.patch(url, json={"expected_version": 1, "layout_id": "cover"}).status_code == 400
    over = client.patch(url, json={"expected_version": 1, "title": "가" * 30}).json()["data"][
        "card"
    ]
    assert over["over_limit"] == ["title"] and over["version"] == 2
    assert (
        client.patch(
            f"{BASE}/documents/{doc_id}/cards/C99", json={"expected_version": 1}
        ).status_code
        == 404
    )


def test_card_stage_check_and_repair(make_client):
    """기본 검사는 카드 단계(요약 ↔ 카드 문구). 수정안은 /repair 로 조회해 PATCH 한다."""
    client, pipeline = make_client()
    doc_id = generated(client)
    # 검사 전에는 수정안이 없다
    assert client.post(f"{BASE}/documents/{doc_id}/cards/C2/repair").status_code == 404

    url = f"{BASE}/documents/{doc_id}/cards/C2"
    client.patch(url, json={"expected_version": 1, "body": "매월 999만 원을 줍니다."})
    res = client.post(f"{BASE}/documents/{doc_id}/checks", json={})
    assert res.status_code == 202 and res.json()["data"]["card_ids"] == ["C2", "C3"]
    groups, cards = pipeline.card_inputs
    assert [g["group_id"] for g in groups] == ["G1", "G3"]  # 선택한 그룹만
    assert [c["card_id"] for c in cards] == ["C1", "C2", "C3", "C4"]  # 완전성은 카드 전체를 본다

    cards = {
        c["card_id"]: c
        for c in client.get(f"{BASE}/documents/{doc_id}/cards").json()["data"]["cards"]
    }
    c2, c3 = cards["C2"], cards["C3"]
    assert c2["status"] == "bad" and c2["check"]["factuality_status"] == "POSSIBLE_DISTORTION"
    assert c2["check"]["issues"][0]["suggested_text"] == "매월 10만 원을 저축합니다."
    assert c2["check"]["repair_fields"] == {"body": "매월 10만 원을 저축합니다."}
    assert c2["check"]["checker"].startswith("card-factuality-llm")
    assert c3["status"] == "ok" and c3["check"]["repair_fields"] is None
    assert cards["C1"]["status"] == "unchecked"  # 표지는 검사 대상이 아니다

    repair = client.post(f"{BASE}/documents/{doc_id}/cards/C2/repair").json()["data"]
    assert repair == {
        "card_id": "C2",
        "expected_version": 2,
        "fields": {"body": "매월 10만 원을 저축합니다."},
    }
    fixed = client.patch(
        url, json={"expected_version": repair["expected_version"], **repair["fields"]}
    )
    assert (
        fixed.json()["data"]["card"]["version"] == 3
        and fixed.json()["data"]["card"]["status"] == "pending"
    )


def test_repair_fields_mapping():
    from backend.services.workflow import _repair_fields

    card = {"items": ["a", "b", "c"], "left": {"label": "기존", "value": "6개월"}}
    assert _repair_fields(card, {"items[1]": "B", "title": "T"}) == {
        "items": ["a", "B", "c"],
        "title": "T",
    }
    assert _repair_fields(card, {"left": "기존 — 12개월"}) == {
        "left": {"label": "기존", "value": "12개월"}
    }
    assert _repair_fields(card, {"left": "12개월"}) == {
        "left": {"label": "기존", "value": "12개월"}
    }
    assert _repair_fields(card, {}) is None


def test_not_ready_features_return_501(make_client):
    client, _ = make_client()
    doc_id = generated(client)
    assert client.get(f"{BASE}/documents/{doc_id}/cards/C2/png").status_code == 501


def test_repo_check_wiring_with_fake_openai():
    """RepoPipeline.check가 레포 check_consistency를 실제로 부르는지 가짜 OpenAI로 확인한다."""
    from ai.verification.consistency.checker import JudgmentResult

    class FakeResponses:
        def parse(self, **kwargs):
            items = json.loads(kwargs["input"][1]["content"])["items"]
            parsed = JudgmentResult(
                judgments=[
                    {"item_id": i["item_id"], "supported": True, "problems": []} for i in items
                ]
            )
            return SimpleNamespace(
                output_parsed=parsed,
                model="fake",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    client = SimpleNamespace(responses=FakeResponses())
    results = RepoPipeline(client=client).check(
        [
            {
                "item_id": "C2",
                "source": "월 10만 원을 저축한다.",
                "text": "월 10만 원을 저축합니다.",
            },
            {
                "item_id": "C3",
                "source": "월 10만 원을 저축한다.",
                "text": "월 20만 원을 저축합니다.",
            },
        ]
    )
    assert [(r["item_id"], r["status"], r["by"]) for r in results] == [
        ("C2", "PASS", "llm"),
        ("C3", "FAIL", "rule"),
    ]


def test_repo_check_cards_wiring_with_fake_openai():
    """check_cards가 사실성·완전성·피드백 함수를 실제로 부르는지 가짜 OpenAI로 확인한다."""
    from ai.verification.completeness.llm.llm_checker import CoverageResponse
    from ai.verification.factuality.llm.llm_checker import LLMCardResponse
    from ai.verification.feedback.merger import FeedbackResponse

    class FakeResponses:
        def parse(self, **kwargs):
            fmt, payload = kwargs["text_format"], json.loads(kwargs["input"])
            if fmt is LLMCardResponse:
                parsed = LLMCardResponse(
                    results=[
                        {
                            "unit_id": f["unit_id"],
                            "status": "POSSIBLE_DISTORTION"
                            if "999" in f["card_text"]
                            else "SUPPORTED",
                            "evidence": "월 10만 원",
                            "reason": "금액이 다릅니다." if "999" in f["card_text"] else "",
                            "error_type": "수치 변경" if "999" in f["card_text"] else None,
                            "suggested_text": "월 10만 원을 저축합니다."
                            if "999" in f["card_text"]
                            else None,
                        }
                        for f in payload["fields"]
                    ]
                )
            elif fmt is CoverageResponse:
                parsed = CoverageResponse(
                    results=[
                        {
                            "fact_id": f["fact_id"],
                            "status": "COVERED",
                            "matched_card_ids": [c["card_id"] for c in payload["cards"]],
                            "reason": "",
                            "missing_elements": [],
                        }
                        for f in payload["required_facts"]
                    ]
                )
            else:
                parsed = FeedbackResponse(
                    items=[
                        {
                            "title": "금액 수정",
                            "category": "ERROR",
                            "description": "999만 원은 요약과 다릅니다.",
                            "suggested_text": "월 10만 원을 저축합니다.",
                            "source_ids": [f["source_id"] for f in payload["findings"]],
                            "card_ids": ["C2"],
                        }
                    ]
                )
            return SimpleNamespace(
                output_parsed=parsed,
                model="fake",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    groups = [
        {
            "group_id": "G1",
            "sentence_ids": ["S1"],
            "summary": "월 10만 원을 저축한다.",
            "topic": "t",
            "headline": "h",
        }
    ]
    cards = [
        {
            "card_id": "C1",
            "group_id": None,
            "layout_id": "cover",
            "sids": [],
            "title": "표지",
            "category": "c",
            "image_query": "q",
        },
        {
            "card_id": "C2",
            "group_id": "G1",
            "layout_id": "body",
            "sids": ["S1"],
            "title": "저축",
            "body": "월 999만 원을 저축합니다.",
            "image_query": "q",
        },
    ]
    result = RepoPipeline(client=SimpleNamespace(responses=FakeResponses())).check_cards(
        "doc", groups, cards
    )
    assert result["cards"]["C1"]["status"] == "NOT_CHECKED"
    assert result["cards"]["C2"]["status"] == "POSSIBLE_DISTORTION"
    body = next(f for f in result["cards"]["C2"]["fields"] if f["field_path"] == "body")
    assert body["suggested_text"] == "월 10만 원을 저축합니다."
    assert result["completeness"][0]["fact_id"] == "G1:summary"
    assert result["feedback"][0]["card_ids"] == ["C2"] and result["status"] == "ISSUES_FOUND"
