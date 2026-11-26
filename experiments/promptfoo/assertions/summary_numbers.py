"""요약 단계 숫자 규칙 assertion.

promptfoo Python assertion 규약: get_assert(output, context) 또는 지정 함수가
{"pass", "score", "reason"} 딕셔너리를 돌려준다. 원문은 context["vars"]["source"]에서 읽는다.
기존 서비스 규칙(ai/verification/consistency/numbers.py)을 그대로 호출해
규칙이 둘로 갈라지지 않게 한다.
"""

from ai.verification.consistency.numbers import find_missing_numbers, find_new_numbers


def _source(context) -> str:
    return str(context["vars"]["source"])


def no_new_numbers(output: str, context) -> dict:
    """원문에 없는 숫자가 요약에 생기면 실패 (사실성 보조 규칙)."""
    new = find_new_numbers(_source(context), output)
    if new:
        return {"pass": False, "score": 0.0, "reason": f"원문에 없는 숫자: {', '.join(new)}"}
    return {"pass": True, "score": 1.0, "reason": "새 숫자 없음"}


def keeps_source_numbers(output: str, context) -> dict:
    """원문 숫자가 요약에서 빠지면 실패 (보존용 Summary의 누락 보조 규칙)."""
    missing = find_missing_numbers(_source(context), output)
    if missing:
        return {"pass": False, "score": 0.0, "reason": f"빠진 원문 숫자: {', '.join(missing)}"}
    return {"pass": True, "score": 1.0, "reason": "원문 숫자 모두 남음"}


def get_assert(output: str, context) -> dict:
    return no_new_numbers(output, context)
