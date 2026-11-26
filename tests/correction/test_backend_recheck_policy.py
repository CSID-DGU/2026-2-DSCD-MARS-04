import pytest

from ai.correction.policy import AI_REPAIR
from backend.core.responses import ApiError
from backend.services import workflow as wf


class CheckPipeline:
    def __init__(self, *, fail=False):
        self.fail = fail

    def check_cards(self, document_id, groups, cards, sentences):
        if self.fail:
            raise RuntimeError("check failed")
        return {
            "status": "OK",
            "model": "fake",
            "cards": {
                "C1": {
                    "status": "SUPPORTED",
                    "fields": [],
                }
            },
            "completeness": [],
            "feedback": [],
        }


@pytest.fixture
def make_store(store):
    return lambda: _seed(store)


def _seed(store):
    store.save_document(
        {
            "document_id": "doc-1",
            "user_id": "user-1",
            "status": "generated",
            "required_group_ids": ["G1"],
            "groups": [{"group_id": "G1", "summary": "요약"}],
        }
    )
    store.replace_cards(
        "doc-1",
        [
            {
                "card_id": "C1",
                "db_id": "doc-1:C1",
                "document_id": "doc-1",
                "order": 1,
                "version": 1,
                "generated_by": "llm",
                "group_id": "G1",
                "layout_id": "body",
                "sids": ["S1"],
                "image_query": "saving",
                "title": "저축 지원",
                "category": None,
                "body": "매월 10만 원을 저축합니다.",
                "items": None,
                "left": None,
                "right": None,
                "cta": None,
                "image": None,
                "ai_recheck_count": 0,
                "manual_final_check_used": False,
                "pending_edit_source": None,
            }
        ],
    )
    return store


def run_card_check(store, pipeline=None):
    pipeline = pipeline or CheckPipeline()
    job, card_ids = wf.start_check(store, "doc-1", ["C1"])
    wf.run_job(store, job, wf.check_work(store, pipeline, "doc-1", card_ids))
    return store.get_card("doc-1:C1")


def edit(store, *, source="manual", version=None):
    card = store.get_card("doc-1:C1")
    return wf.update_card(
        store,
        "doc-1",
        "C1",
        {
            "expected_version": version or card["version"],
            "body": f"수정 문구 {card['version']}",
            "edit_source": source,
        },
        {},
    )


def test_initial_check_does_not_use_recheck_count(make_store):
    card = run_card_check(make_store())

    assert card["ai_recheck_count"] == 0
    assert card["manual_final_check_used"] is False
    assert card["pending_edit_source"] is None


def test_ai_recheck_is_limited_to_two_successful_checks(make_store):
    store = make_store()
    run_card_check(store)

    edit(store, source=AI_REPAIR)
    assert run_card_check(store)["ai_recheck_count"] == 1
    edit(store, source=AI_REPAIR)
    assert run_card_check(store)["ai_recheck_count"] == 2

    with pytest.raises(ApiError):
        edit(store, source=AI_REPAIR)


def test_manual_final_check_is_allowed_once_separately(make_store):
    store = make_store()
    run_card_check(store)

    edit(store)
    card = run_card_check(store)
    assert card["manual_final_check_used"] is True
    assert card["ai_recheck_count"] == 0
    edit(store)

    with pytest.raises(ApiError):
        wf.start_check(store, "doc-1", ["C1"])


def test_failed_ai_recheck_does_not_increase_count(make_store):
    store = make_store()
    run_card_check(store)
    edit(store, source=AI_REPAIR)

    job, card_ids = wf.start_check(store, "doc-1", ["C1"])
    wf.run_job(store, job, wf.check_work(store, CheckPipeline(fail=True), "doc-1", card_ids))
    card = store.get_card("doc-1:C1")

    assert job["status"] == "failed"
    assert card["ai_recheck_count"] == 0
    assert card["pending_edit_source"] == AI_REPAIR
