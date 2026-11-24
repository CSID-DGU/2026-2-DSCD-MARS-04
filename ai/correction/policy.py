"""카드 문구 수정 후 재검사 횟수를 관리하는 순수 정책 모듈.

정책
----
* 최초 검사는 재검사 횟수에 포함하지 않는다.
* AI 수정안을 적용한 뒤의 재검사는 카드당 최대 2회 허용한다.
* 사용자 직접 수정 뒤에는 최종 검사를 1회 별도로 허용한다.
* 검사 요청 실패는 이 모듈의 기록 함수를 호출하지 않으므로 횟수에 포함되지 않는다.
* 카드 재생성 시 호출부가 카운터와 플래그를 초기값으로 다시 저장한다.

이 모듈은 저장소나 HTTP 요청을 직접 다루지 않는다. 호출부는 검사가 성공적으로
완료된 뒤에만 :func:`record_successful_check`의 반환값을 카드에 저장해야 한다.
"""

from dataclasses import dataclass
from typing import Literal

MAX_AI_RECHECKS = 2
MAX_MANUAL_FINAL_CHECKS = 1

INITIAL = "initial"
AI_RECHECK = "ai_recheck"
MANUAL_FINAL = "manual_final"

AI_REPAIR = "ai_repair"
MANUAL = "manual"

AI_RECHECK_LIMIT_REACHED = "ai_recheck_limit_reached"
MANUAL_FINAL_CHECK_USED = "manual_final_check_used"
CARD_NOT_EDITED = "card_not_edited"

type CheckKind = Literal["initial", "ai_recheck", "manual_final"]
type EditSource = Literal["ai_repair", "manual"]
type BlockReason = Literal[
    "ai_recheck_limit_reached",
    "manual_final_check_used",
    "card_not_edited",
]


@dataclass(frozen=True, slots=True)
class CheckPermission:
    """검사 가능 여부와 차단 사유."""

    allowed: bool
    reason: BlockReason | None = None


def classify_check(
    *,
    has_previous_check: bool,
    pending_edit_source: str | None,
) -> CheckKind:
    """카드 상태를 이번 검사의 종류로 변환한다.

    첫 검사 전의 문구 수정은 재검사로 세지 않는다. 이미 검사를 마친 카드라면
    마지막 문구 변경 주체가 반드시 기록되어 있어야 한다.
    """

    if not isinstance(has_previous_check, bool):
        raise TypeError("has_previous_check는 bool이어야 합니다.")

    if not has_previous_check:
        return INITIAL
    if pending_edit_source == AI_REPAIR:
        return AI_RECHECK
    if pending_edit_source == MANUAL:
        return MANUAL_FINAL
    if pending_edit_source is None:
        raise ValueError("검사 이후 수정되지 않은 카드입니다.")
    raise ValueError(f"지원하지 않는 수정 출처입니다: {pending_edit_source!r}")


def remaining_ai_rechecks(
    ai_recheck_count: int,
    *,
    max_ai_rechecks: int = MAX_AI_RECHECKS,
) -> int:
    """남은 AI 수정안 재검사 횟수를 반환한다."""

    _validate_non_negative_int("ai_recheck_count", ai_recheck_count)
    _validate_non_negative_int("max_ai_rechecks", max_ai_rechecks)
    return max(max_ai_rechecks - ai_recheck_count, 0)


def can_apply_ai_repair(
    ai_recheck_count: int,
    *,
    max_ai_rechecks: int = MAX_AI_RECHECKS,
) -> bool:
    """AI 수정안을 적용하고 다시 검사할 기회가 남았는지 반환한다."""

    return (
        remaining_ai_rechecks(
            ai_recheck_count,
            max_ai_rechecks=max_ai_rechecks,
        )
        > 0
    )


def check_permission(
    *,
    check_kind: CheckKind,
    ai_recheck_count: int,
    manual_final_check_used: bool,
    max_ai_rechecks: int = MAX_AI_RECHECKS,
) -> CheckPermission:
    """검사 종류와 현재 사용 횟수를 바탕으로 실행 가능 여부를 판단한다."""

    _validate_non_negative_int("ai_recheck_count", ai_recheck_count)
    _validate_non_negative_int("max_ai_rechecks", max_ai_rechecks)
    if not isinstance(manual_final_check_used, bool):
        raise TypeError("manual_final_check_used는 bool이어야 합니다.")

    if check_kind == INITIAL:
        return CheckPermission(allowed=True)
    if check_kind == AI_RECHECK:
        if ai_recheck_count >= max_ai_rechecks:
            return CheckPermission(False, AI_RECHECK_LIMIT_REACHED)
        return CheckPermission(allowed=True)
    if check_kind == MANUAL_FINAL:
        if manual_final_check_used:
            return CheckPermission(False, MANUAL_FINAL_CHECK_USED)
        return CheckPermission(allowed=True)
    raise ValueError(f"지원하지 않는 검사 종류입니다: {check_kind!r}")


def can_run_check(
    *,
    check_kind: CheckKind,
    ai_recheck_count: int,
    manual_final_check_used: bool,
    max_ai_rechecks: int = MAX_AI_RECHECKS,
) -> bool:
    """이번 검사를 실행할 수 있는지만 간단히 반환한다."""

    return check_permission(
        check_kind=check_kind,
        ai_recheck_count=ai_recheck_count,
        manual_final_check_used=manual_final_check_used,
        max_ai_rechecks=max_ai_rechecks,
    ).allowed


def record_successful_check(
    *,
    check_kind: CheckKind,
    ai_recheck_count: int,
    manual_final_check_used: bool,
    max_ai_rechecks: int = MAX_AI_RECHECKS,
) -> tuple[int, bool]:
    """성공한 검사 결과를 반영한 ``(AI 횟수, 사용자 최종 검사 여부)``를 반환한다.

    검사 API 오류, 파싱 오류처럼 검사가 완료되지 않은 경우에는 호출하면 안 된다.
    허용 횟수를 초과한 검사를 기록하려 하면 ``ValueError``를 발생시킨다.
    """

    permission = check_permission(
        check_kind=check_kind,
        ai_recheck_count=ai_recheck_count,
        manual_final_check_used=manual_final_check_used,
        max_ai_rechecks=max_ai_rechecks,
    )
    if not permission.allowed:
        raise ValueError(f"검사를 기록할 수 없습니다: {permission.reason}")

    if check_kind == AI_RECHECK:
        return ai_recheck_count + 1, manual_final_check_used
    if check_kind == MANUAL_FINAL:
        return ai_recheck_count, True
    return ai_recheck_count, manual_final_check_used


def _validate_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name}는 int여야 합니다.")
    if value < 0:
        raise ValueError(f"{name}는 0 이상이어야 합니다.")
