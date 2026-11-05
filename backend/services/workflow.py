"""문서·카드·검사 상태 전이. API 계층은 이 함수들만 부른다."""

from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from backend.core.responses import ApiError
from backend.core.store import Store, new_id, now
from backend.services.pipeline import CARD_CHECKER_NAME, CHECKER_NAME, Pipeline
from data_pipeline.schemas.card import CardGeneration

LAYOUT_FIELDS = ("title", "category", "body", "items", "left", "right", "cta")
MAX_TEXT_CHARS = 20_000
CLOSING_TITLE = "원문에서 확인하세요"
CLOSING_BODY = "자세한 조건과 신청 방법은 원문을 확인해 주세요."
CLOSING_CTA = "원문 보기"


# ---------------- 조회용 변환 ----------------


def card_view(store: Store, card: dict) -> dict:
    """저장된 카드에 검사 상태를 계산해 붙인다. 판정은 version이 같을 때만 유효하다."""
    check = store.latest_check(card["db_id"])
    if check is None:
        status, valid = "unchecked", None
    elif check["card_version"] != card["version"]:
        status, valid = "pending", None
    else:
        status, valid = check["verdict"], check
    view = {k: v for k, v in card.items() if k != "db_id"}
    view.update(status=status, check=valid)
    return view


def doc_view(doc: dict) -> dict:
    return {
        k: doc[k]
        for k in ("document_id", "status", "source", "sentences", "groups", "required_group_ids")
    }


def require_document(store: Store, document_id: str, *, analyzed: bool = False) -> dict:
    doc = store.get_document(document_id)
    if doc is None:
        raise ApiError(404, "존재하지 않는 문서입니다.")
    if analyzed and doc["status"] in ("analyzing", "analysis_failed"):
        raise ApiError(
            409,
            "아직 분석 중인 문서입니다."
            if doc["status"] == "analyzing"
            else "분석에 실패한 문서입니다.",
        )
    return doc


def find_card(store: Store, document_id: str, card_id: str) -> dict:
    """card_id(C1…)는 문서 안에서만 고유하므로 문서 ID와 함께 찾는다."""
    require_document(store, document_id)
    card = store.get_card(f"{document_id}:{card_id}")
    if card is None:
        raise ApiError(404, "존재하지 않는 카드입니다.")
    return card


# ---------------- 작업 공통 ----------------


def start_job(store: Store, kind: str, document_id: str) -> dict:
    if store.active_job(document_id):
        raise ApiError(409, "다른 작업이 진행 중입니다.")
    job = {
        "job_id": new_id("job"),
        "kind": kind,
        "document_id": document_id,
        "status": "queued",
        "stage": None,
        "error": None,
        "started_at": now(),
        "finished_at": None,
        "elapsed_seconds": None,
    }
    store.save_job(job)
    return job


def run_job(store: Store, job: dict, work) -> None:
    started = time.perf_counter()

    def stage(name: str) -> None:
        job.update(status="running", stage=name)
        store.save_job(job)

    try:
        stage("start")
        work(stage)
        job.update(status="succeeded")
    except Exception as exc:  # 오류 본문에는 원문·키가 섞일 수 있어 종류와 단계만 남긴다
        job.update(status="failed", error={"type": type(exc).__name__, "stage": job.get("stage")})
        raise_for_doc = {"analysis": "analysis_failed", "generation": "generation_failed"}.get(
            job["kind"]
        )
        if raise_for_doc:
            doc = store.get_document(job["document_id"])
            if doc:
                doc["status"] = raise_for_doc
                store.save_document(doc)
    finally:
        job.update(finished_at=now(), elapsed_seconds=round(time.perf_counter() - started, 3))
        store.save_job(job)


# ---------------- 문서 ----------------


def create_document(store: Store, body: dict) -> tuple[dict, dict]:
    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "원문이 비어 있습니다.")
    if len(text) > MAX_TEXT_CHARS:
        raise ApiError(413, f"원문이 너무 깁니다. {MAX_TEXT_CHARS:,}자 이하로 입력해 주세요.")
    source = {k: body.get(k) for k in ("title", "source_url", "source_name", "license")}
    doc = {
        "document_id": new_id("doc"),
        "text": text,
        "source": source,
        "status": "analyzing",
        "sentences": [],
        "groups": [],
        "required_group_ids": [],
        "selection_version": 0,
        "cards_selection_version": None,
        "created_at": now(),
    }
    store.save_document(doc)
    return doc, start_job(store, "analysis", doc["document_id"])


def analysis_work(store: Store, pipeline: Pipeline, document_id: str):
    def work(stage):
        doc = require_document(store, document_id)
        stage("split")
        sentences = pipeline.split(doc["text"])
        stage("analysis")
        groups = pipeline.analyze(document_id, doc["text"])
        stage("titles")
        groups = pipeline.titles(document_id, groups)
        known = {s["sentence_id"] for s in sentences}
        if any(sid not in known for g in groups for sid in g["sentence_ids"]):
            raise RuntimeError("그룹의 문장 ID가 문장 목록과 맞지 않습니다.")
        stage("summary_check")
        groups = _check_summaries(pipeline, sentences, groups)
        doc.update(sentences=sentences, groups=groups, status="analyzed")
        store.save_document(doc)

    return work


def _check_summaries(pipeline: Pipeline, sentences: list[dict], groups: list[dict]) -> list[dict]:
    """요약 단계 검사: 그룹 문장(원문) ↔ 그룹 요약. consistency 검사기(숫자 규칙 + LLM).

    결과는 group.summary_check 로 붙인다. FAIL 처리 방식(선택 차단·경고·재생성)은 팀 결정 전이라
    상태만 기록한다. 검사 자체가 실패해도 분석 결과는 살린다.
    """
    text_of = {s["sentence_id"]: s["text"] for s in sentences}
    items = [
        {
            "item_id": g["group_id"],
            "source": " ".join(text_of[s] for s in g["sentence_ids"] if s in text_of),
            "text": g.get("summary") or "",
        }
        for g in groups
    ]
    items = [i for i in items if i["text"].strip()]
    checks: dict[str, dict] = {}
    try:
        for r in pipeline.check(items):
            checks[r["item_id"]] = {
                "verdict": "ok" if r["status"] == "PASS" else "bad",
                "by": r.get("by"),
                "problems": r.get("problems", []),
                "checker": CHECKER_NAME,
            }
    except Exception as exc:  # noqa: BLE001 — 검사 실패는 분석 실패가 아니다
        error = {"verdict": "error", "by": None, "problems": [], "checker": CHECKER_NAME}
        error["error"] = type(exc).__name__
        checks = {i["item_id"]: dict(error) for i in items}
    return [{**g, "summary_check": checks.get(g["group_id"])} for g in groups]


# ---------------- 선택 ----------------


def save_selection(store: Store, document_id: str, ids: list[str]) -> dict:
    doc = require_document(store, document_id, analyzed=True)
    if not ids:
        raise ApiError(400, "선택된 그룹이 없습니다.")
    if len(ids) != len(set(ids)):
        raise ApiError(400, "선택된 그룹 ID가 중복되었습니다.")
    order = [g["group_id"] for g in doc["groups"]]
    invalid = [i for i in ids if i not in order]
    if invalid:
        raise ApiError(400, f"존재하지 않는 그룹 ID: {invalid}")
    ordered = [g for g in order if g in ids]
    if ordered != doc["required_group_ids"]:
        doc["selection_version"] += 1
    doc["required_group_ids"] = ordered
    store.save_document(doc)
    has_cards = bool(store.list_cards(document_id))
    outdated = has_cards and doc["cards_selection_version"] != doc["selection_version"]
    return {"document_id": document_id, "required_group_ids": ordered, "cards_outdated": outdated}


# ---------------- 카드 ----------------


def start_generation(store: Store, document_id: str, overwrite: bool) -> dict:
    doc = require_document(store, document_id, analyzed=True)
    if not doc["required_group_ids"]:
        raise ApiError(400, "선택된 그룹이 없습니다.")
    if store.list_cards(document_id) and not overwrite:
        raise ApiError(409, "이미 만든 카드가 있습니다. 다시 만들려면 overwrite=true로 요청하세요.")
    job = start_job(store, "generation", document_id)
    doc["status"] = "generating"
    store.save_document(doc)
    return job


def _template_cards(doc: dict, groups: list[dict]) -> tuple[dict, dict]:
    title = doc["source"].get("title") or groups[0]["topic"]
    cover = {
        "group_id": None,
        "layout_id": "cover",
        "sids": [],
        "title": title,
        "category": groups[0]["topic"],
        "image_query": "public policy announcement",
    }
    closing = {
        "group_id": None,
        "layout_id": "closing",
        "sids": [],
        "title": CLOSING_TITLE,
        "body": CLOSING_BODY,
        "cta": CLOSING_CTA,
        "image_query": "reading news on phone",
    }
    return cover, closing


def generation_work(store: Store, pipeline: Pipeline, document_id: str):
    def work(stage):
        doc = require_document(store, document_id)
        groups = [g for g in doc["groups"] if g["group_id"] in doc["required_group_ids"]]
        stage("cards")
        body_cards = pipeline.generate(document_id, groups)
        cover, closing = _template_cards(doc, groups)
        cards = []
        sequence = (
            [(cover, "template")] + [(c, "llm") for c in body_cards] + [(closing, "template")]
        )
        stage("images")
        for order, (raw, by) in enumerate(sequence, 1):
            fields = CardGeneration.model_validate(raw).model_dump()
            card_id = f"C{order}"
            cards.append(
                {
                    **fields,
                    "card_id": card_id,
                    "db_id": f"{document_id}:{card_id}",
                    "document_id": document_id,
                    "order": order,
                    "version": 1,
                    "generated_by": by,
                    "image": _photo(pipeline, fields["image_query"]),
                }
            )
        store.replace_cards(document_id, cards)
        doc.update(status="generated", cards_selection_version=doc["selection_version"])
        store.save_document(doc)

    return work


def _photo(pipeline: Pipeline, query: str) -> dict | None:
    """사진 검색 실패는 카드 생성을 막지 않는다. 없으면 None(프론트는 기본 배경)."""
    try:
        return pipeline.photo(query)
    except Exception as exc:  # noqa: BLE001
        return {"stage": "none", "query": query, "message": f"사진 검색 실패: {type(exc).__name__}"}


def over_limit(card: dict, layouts: dict) -> list[str]:
    spec = layouts.get("layouts", {}).get(card["layout_id"], {}).get("fields", {})
    out = []
    for name, rule in spec.items():
        value, limit = card.get(name), rule.get("max_chars")
        if limit and isinstance(value, str) and len(value.replace("\n", "")) > limit:
            out.append(name)
    return out


def update_card(store: Store, document_id: str, card_id: str, body: dict, layouts: dict) -> dict:
    card = find_card(store, document_id, card_id)
    expected = body.get("expected_version")
    if expected is None:
        raise ApiError(400, "expected_version이 필요합니다.")
    if expected != card["version"]:
        raise ApiError(409, "다른 곳에서 먼저 수정했습니다. 새로 고친 뒤 다시 시도하세요.")
    locked = {"layout_id", "sids", "group_id", "card_id"} & set(body)
    if locked:
        raise ApiError(400, f"바꿀 수 없는 필드입니다: {sorted(locked)}")
    changes = {k: body[k] for k in LAYOUT_FIELDS if k in body}
    if not changes:
        raise ApiError(400, "바꿀 필드가 없습니다.")
    candidate = {
        k: card.get(k) for k in ("group_id", "layout_id", "sids", "image_query", *LAYOUT_FIELDS)
    }
    candidate.update(changes)
    try:
        fields = CardGeneration.model_validate(candidate).model_dump()
    except ValidationError as exc:
        reason = exc.errors()[0].get("msg", "").removeprefix("Value error, ")
        raise ApiError(400, reason or "카드 형식이 올바르지 않습니다.") from None
    if all(fields[k] == card.get(k) for k in LAYOUT_FIELDS):
        view = card_view(store, card)
        view["over_limit"] = over_limit(card, layouts)
        return view
    card.update({k: fields[k] for k in LAYOUT_FIELDS})
    card.update(version=card["version"] + 1, generated_by="user")
    store.save_card(card)
    view = card_view(store, card)
    view["over_limit"] = over_limit(card, layouts)
    return view


# ---------------- 검사 ----------------


def card_text(card: dict) -> str:
    parts: list[Any] = [card.get("category"), card.get("title"), card.get("body"), card.get("cta")]
    parts += card.get("items") or []
    for side in ("left", "right"):
        if card.get(side):
            parts.append(f"{card[side].get('label', '')}: {card[side].get('value', '')}")
    return "\n".join(p for p in parts if p)


def start_check(
    store: Store, document_id: str, card_ids: list[str] | None
) -> tuple[dict, list[str]]:
    require_document(store, document_id, analyzed=True)
    cards = [card_view(store, c) | {"db_id": c["db_id"]} for c in store.list_cards(document_id)]
    if card_ids:
        known = {c["card_id"] for c in cards}
        missing = [i for i in card_ids if i not in known]
        if missing:
            raise ApiError(400, f"존재하지 않는 카드 ID: {missing}")
        targets = [c for c in cards if c["card_id"] in card_ids]
    else:
        targets = [c for c in cards if c["status"] in ("unchecked", "pending")]
    targets = [c for c in targets if c["sids"]]
    if not targets:
        raise ApiError(409, "검사할 카드가 없습니다.")
    return start_job(store, "check", document_id), [c["card_id"] for c in targets]


def check_work(store: Store, pipeline: Pipeline, document_id: str, card_ids: list[str]):
    """카드 단계 검사: 그룹 요약 ↔ 카드 문구. 수연 사실성·완전성·피드백 통합(pipeline.check_cards).

    완전성은 그룹의 카드 전체를 봐야 하므로 그룹 카드 전부를 넘기고, 판정은 card_ids에만 저장한다.
    """

    def work(stage):
        doc = require_document(store, document_id)
        all_cards = store.list_cards(document_id)
        versions = {c["card_id"]: c["version"] for c in all_cards}
        selected = set(doc["required_group_ids"])
        groups = [g for g in doc["groups"] if g["group_id"] in selected]
        stage("check")
        result = pipeline.check_cards(document_id, groups, [_card_input(c) for c in all_cards])
        checked_at = now()
        by_card = result.get("cards", {})
        completeness = result.get("completeness", [])
        feedback = result.get("feedback", [])
        for cid in card_ids:
            card = store.get_card(f"{document_id}:{cid}")
            if card is None or card["version"] != versions[cid]:
                continue  # 검사 중에 문구가 바뀌면 이 판정은 저장하지 않는다
            store.save_check(
                card["db_id"],
                _card_check(card, by_card.get(cid), completeness, feedback, result, checked_at),
            )

    return work


def _card_input(card: dict) -> dict:
    keys = ("card_id", "group_id", "layout_id", "sids", "image_query", *LAYOUT_FIELDS)
    return {k: card.get(k) for k in keys}


FACT_VERDICT = {
    "SUPPORTED": "ok",
    "NON_ASSERTIVE": "ok",
    "POSSIBLE_DISTORTION": "bad",
    "INSUFFICIENT_EVIDENCE": "warn",
    "UNCERTAIN": "warn",
    "NOT_CHECKED": "ok",
}
FACT_LABEL = {
    "POSSIBLE_DISTORTION": "의미 왜곡 가능",
    "INSUFFICIENT_EVIDENCE": "근거 부족",
    "UNCERTAIN": "판단 보류",
}
COVER_LABEL = {
    "MISSING": "필수 정보 누락",
    "PARTIALLY_COVERED": "일부만 반영",
    "DISTORTED": "필수 정보 왜곡",
    "UNCERTAIN": "반영 여부 불확실",
}


def _card_check(card, fact, completeness, feedback, result, checked_at) -> dict:
    """수연 검사 결과를 카드 한 장의 check 레코드로 바꾼다. 수정안은 필드별 suggested_text."""
    fact = fact or {"status": "NOT_CHECKED", "fields": []}
    issues, suggested = [], {}
    for f in fact["fields"]:
        if f["status"] in FACT_LABEL:
            issues.append(
                {
                    "type": f.get("error_type") or FACT_LABEL[f["status"]],
                    "field_path": f["field_path"],
                    "card_span": f["card_text"],
                    "source_span": f.get("evidence") or "",
                    "explanation": f.get("reason") or "",
                    "suggested_text": f.get("suggested_text"),
                }
            )
        if f.get("suggested_text"):
            suggested[f["field_path"]] = f["suggested_text"]
    cid = card["card_id"]
    cover = [
        c
        for c in completeness
        if cid in c.get("matched_card_ids", []) or c.get("group_id") == card.get("group_id")
    ]
    cover_issues = [
        {
            "type": COVER_LABEL[c["status"]],
            "fact_id": c["fact_id"],
            "explanation": c.get("reason") or "",
            "missing_elements": c.get("missing_elements", []),
        }
        for c in cover
        if c["status"] in COVER_LABEL
    ]
    verdict = FACT_VERDICT.get(fact["status"], "warn")
    if verdict == "ok" and any(c["status"] in ("MISSING", "DISTORTED") for c in cover):
        verdict = "warn"
    return {
        "card_id": cid,
        "card_version": card["version"],
        "verdict": verdict,
        "by": "llm",
        "factuality_status": fact["status"],
        "issues": issues,
        "completeness": cover_issues,
        "repair_fields": _repair_fields(card, suggested),
        "feedback": [i for i in feedback if cid in i.get("card_ids", [])],
        "checker": f"{CARD_CHECKER_NAME}/{result.get('model', '')}",
        "checked_at": checked_at,
    }


def _repair_fields(card: dict, suggested: dict[str, str]) -> dict | None:
    """field_path(title, body, items[2], left, right)별 수정안을 PATCH 가능한 필드 묶음으로."""
    if not suggested:
        return None
    out: dict[str, Any] = {}
    for path, text in suggested.items():
        if path in ("title", "body", "cta", "category"):
            out[path] = text
        elif path.startswith("items["):
            items = list(out.get("items") or card.get("items") or [])
            i = int(path[6:-1])
            if 0 <= i < len(items):
                items[i] = text
                out["items"] = items
        elif path in ("left", "right"):
            side = dict(card.get(path) or {})
            label, _, value = text.partition(" — ")
            if value:
                side.update(label=label.strip(), value=value.strip())
            else:
                side["value"] = text.strip()
            out[path] = side
    return out or None


def summary_check_work(store: Store, pipeline: Pipeline, document_id: str, card_ids: list[str]):
    """요약 단계 검사(원문 문장 ↔ 문구)를 카드 문구에 적용하는 이전 방식. consistency 검사기."""

    def work(stage):
        doc = require_document(store, document_id)
        order = {s["sentence_id"]: i for i, s in enumerate(doc["sentences"])}
        text_of = {s["sentence_id"]: s["text"] for s in doc["sentences"]}
        cards = {c["card_id"]: c for c in store.list_cards(document_id)}
        items, versions = [], {}
        for cid in card_ids:
            card = cards[cid]
            sids = sorted(card["sids"], key=lambda s: order.get(s, 10**6))
            items.append(
                {
                    "item_id": cid,
                    "source": " ".join(text_of[s] for s in sids if s in text_of),
                    "text": card_text(card),
                }
            )
            versions[cid] = card["version"]
        stage("check")
        results = pipeline.check(items)
        checked_at = now()
        for result in results:
            cid = result["item_id"]
            card = store.get_card(cards[cid]["db_id"])
            if card is None or card["version"] != versions[cid]:
                continue  # 검사 중에 문구가 바뀌면 이 판정은 저장하지 않는다
            store.save_check(
                card["db_id"],
                {
                    "card_id": cid,
                    "card_version": versions[cid],
                    "verdict": "ok" if result["status"] == "PASS" else "bad",
                    "by": result.get("by"),
                    "problems": result.get("problems", []),
                    "checker": CHECKER_NAME,
                    "checked_at": checked_at,
                },
            )

    return work


# ---------------- 내보내기 ----------------


def build_record(store: Store, document_id: str) -> dict:
    doc = require_document(store, document_id, analyzed=True)
    cards = [card_view(store, c) for c in store.list_cards(document_id)]
    selected = set(doc["required_group_ids"])
    return {
        "exported_at": now(),
        "document_id": document_id,
        "source": doc["source"],
        "sentences": doc["sentences"],
        "groups": [{**g, "selected": g["group_id"] in selected} for g in doc["groups"]],
        "cards": cards,
        "unverified_card_count": sum(1 for c in cards if c["status"] != "ok"),
    }
