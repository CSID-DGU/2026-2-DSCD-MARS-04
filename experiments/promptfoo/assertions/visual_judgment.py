"""시각 평가 결과 JSON 형식 assertion.

판정 내용이 맞는지가 아니라, 평가기가 계약대로 답했는지를 코드로 확인한다.
- 모든 평가 항목(criteria)에 결과가 있는가
- card_ids가 실제 카드 ID인가
- verdict가 허용값인가
- NOT_APPLICABLE에는 이유가 있는가
"""

import json

VERDICTS = {"MET", "NOT_MET", "NOT_APPLICABLE", "UNCERTAIN"}
SCOPES = {"card", "set"}


def _as_list(value) -> list:
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def _fail(problems: list[str]) -> dict:
    return {"pass": False, "score": 0.0, "reason": "; ".join(problems)}


def valid_visual_judgment(output: str, context) -> dict:
    try:
        judgments = json.loads(output)["judgments"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return _fail(['JSON {"judgments": [...]} 형식이 아님'])

    card_ids = set(_as_list(context["vars"]["card_ids"]))
    criteria = _as_list(context["vars"]["criteria"])
    problems: list[str] = []

    for index, item in enumerate(judgments, start=1):
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            problems.append(f"{index}번 판정의 verdict 허용값 아님: {verdict}")
        if item.get("scope") not in SCOPES:
            problems.append(f"{index}번 판정의 scope 허용값 아님: {item.get('scope')}")
        unknown = [cid for cid in item.get("card_ids", []) if cid not in card_ids]
        if unknown:
            problems.append(f"{index}번 판정에 없는 카드 ID: {', '.join(unknown)}")
        if verdict == "NOT_APPLICABLE" and not str(item.get("reason", "")).strip():
            problems.append(f"{index}번 판정: NOT_APPLICABLE에는 reason 필요")

    answered = {item.get("criterion_id") for item in judgments}
    missing = [c for c in criteria if c not in answered]
    if missing:
        problems.append(f"결과 없는 평가 항목: {', '.join(missing)}")

    if problems:
        return _fail(problems)
    return {"pass": True, "score": 1.0, "reason": "평가 결과 형식 통과"}


def get_assert(output: str, context) -> dict:
    return valid_visual_judgment(output, context)
