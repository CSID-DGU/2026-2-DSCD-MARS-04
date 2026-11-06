"""완성 카드 비교 판정 assertion.

1) valid_compare_judgment: 판정이 계약대로 나왔는지 코드로 확인한다
   (판정 내용의 옳고 그름은 보지 않음)
   - 모든 (질문, 카드), (질문, 세트), (C-02, 필수 정보)에 판정이 정확히 하나씩 있는가
   - verdict가 질문 종류별 허용값인가
   - NOT_MET·UNCERTAIN·MISSING·DISTORTED에 evidence가 있고, NOT_APPLICABLE에 reason이 있는가
   - C-01 NOT_MET, C-02 CONVEYED·DISTORTED의 spans에 카드 번호와 문구가 있는가
   - spans의 source_quote가 원문에 실제로 있는가 (공백 차이만 무시)
2) human_agreement: 사람 판정(vars.human)이 있는 사례에서 AI 판정과 같은 비율.
   기준값은 vars.min_agreement
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.promptfoo.compare.common import (
    ai_questions,
    expected_keys,
    judgment_key,
    load_questions,
    normalize,
)

ROOT = Path(__file__).resolve().parents[3]
NEEDS_EVIDENCE = {"NOT_MET", "UNCERTAIN", "MISSING", "DISTORTED"}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def _parse(output: str) -> list[dict] | None:
    try:
        return json.loads(output)["judgments"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _source(vars_: dict) -> str | None:
    if vars_.get("source"):
        return str(vars_["source"])
    if vars_.get("case_dir"):
        path = ROOT / vars_["case_dir"] / "source.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def check_judgments(
    judgments: list[dict], card_ids: list[str], fact_ids: list[str], source: str | None
) -> list[str]:
    spec = load_questions()
    by_id = {q["id"]: q for q in ai_questions(spec)}
    problems: list[str] = []
    seen: dict[tuple, int] = {}

    for n, item in enumerate(judgments, start=1):
        qid = item.get("question_id")
        q = by_id.get(qid)
        if q is None:
            problems.append(f"{n}번: 판정 대상이 아닌 질문 {qid}")
            continue
        key = judgment_key(item)
        seen[key] = seen.get(key, 0) + 1
        verdict = item.get("verdict")
        if verdict not in spec["verdicts"][q["kind"]]:
            problems.append(f"{qid} {key[1] or key[2] or '세트'}: 허용값 아님 {verdict}")
        if key[1] and key[1] not in card_ids:
            problems.append(f"{qid}: 없는 카드 {key[1]}")
        if key[2] and key[2] not in fact_ids:
            problems.append(f"{qid}: 없는 필수 정보 {key[2]}")
        if verdict in NEEDS_EVIDENCE and not str(item.get("evidence", "")).strip():
            problems.append(f"{qid} {key[1] or key[2] or '세트'}: {verdict}인데 evidence 없음")
        if verdict == "NOT_APPLICABLE" and not str(item.get("reason", "")).strip():
            problems.append(f"{qid} {key[1] or '세트'}: NOT_APPLICABLE인데 reason 없음")

        needs_span = (qid == "C-01" and verdict == "NOT_MET") or (
            qid == "C-02" and verdict in {"CONVEYED", "DISTORTED"}
        )
        spans = item.get("spans") or []
        if not isinstance(spans, list) or not all(isinstance(s, dict) for s in spans):
            problems.append(f"{qid} {key[1] or key[2] or '세트'}: spans는 객체 목록이어야 함")
            spans = []
        if needs_span and not spans:
            problems.append(f"{qid} {key[1] or key[2]}: {verdict}인데 spans 없음")
        for span in spans:
            if span.get("card_id") and span["card_id"] not in card_ids:
                problems.append(f"{qid}: spans에 없는 카드 {span['card_id']}")
            if needs_span and not str(span.get("card_text", "")).strip():
                problems.append(f"{qid} {key[1] or key[2]}: spans에 카드 문구 없음")
            quote = str(span.get("source_quote", "")).strip()
            if quote and source is not None and normalize(quote) not in normalize(source):
                problems.append(f"{qid} {key[1] or key[2]}: 원문에 없는 인용 '{quote[:30]}'")

    expected = expected_keys(card_ids, fact_ids, spec)
    missing = sorted(expected - set(seen), key=str)
    if missing:
        shown = ", ".join("/".join(x for x in k if x) for k in missing[:8])
        problems.append(f"판정 누락 {len(missing)}개: {shown}")
    dup = [k for k, c in seen.items() if c > 1]
    if dup:
        shown = ", ".join("/".join(x for x in k if x) for k in dup[:5])
        problems.append(f"중복 판정 {len(dup)}개: {shown}")
    return problems


def valid_compare_judgment(output: str, context) -> dict:
    judgments = _parse(output)
    if judgments is None:
        return {"pass": False, "score": 0.0, "reason": 'JSON {"judgments": [...]} 형식이 아님'}
    vars_ = context["vars"]
    problems = check_judgments(
        judgments, _as_list(vars_["card_ids"]), _as_list(vars_.get("fact_ids")), _source(vars_)
    )
    if problems:
        return {"pass": False, "score": 0.0, "reason": "; ".join(problems)}
    return {"pass": True, "score": 1.0, "reason": f"판정 {len(judgments)}개 형식 통과"}


def agreement(ai: list[dict], human: list[dict]) -> tuple[int, int, list[str]]:
    """사람이 판정한 항목 중 AI 판정이 같은 수. (같음, 비교 수, 다른 항목)"""
    ai_map = {judgment_key(j): j.get("verdict") for j in ai}
    same, total, diff = 0, 0, []
    for h in human:
        key = judgment_key(h)
        if key not in ai_map:
            continue
        total += 1
        if ai_map[key] == h.get("verdict"):
            same += 1
        else:
            diff.append(f"{'/'.join(x for x in key if x)} AI {ai_map[key]} 사람 {h.get('verdict')}")
    return same, total, diff


def human_agreement(output: str, context) -> dict:
    vars_ = context["vars"]
    human = _as_list(vars_.get("human"))
    if not human:
        return {"pass": True, "score": 1.0, "reason": "사람 판정 없음 — 일치도 계산 안 함"}
    judgments = _parse(output) or []
    same, total, diff = agreement(judgments, human)
    if total == 0:
        return {"pass": False, "score": 0.0, "reason": "사람 판정과 겹치는 항목 없음"}
    rate = same / total
    need = float(vars_.get("min_agreement", 0.8))
    reason = f"일치 {same}/{total} ({rate:.0%})"
    if diff:
        reason += " | 다름: " + "; ".join(diff[:6])
    return {"pass": rate >= need, "score": rate, "reason": reason}


def get_assert(output: str, context) -> dict:
    return valid_compare_judgment(output, context)
