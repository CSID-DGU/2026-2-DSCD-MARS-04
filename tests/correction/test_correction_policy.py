import pytest

from ai.correction.policy import (
    AI_RECHECK,
    AI_RECHECK_LIMIT_REACHED,
    AI_REPAIR,
    INITIAL,
    MANUAL,
    MANUAL_FINAL,
    MANUAL_FINAL_CHECK_USED,
    MAX_AI_RECHECKS,
    can_apply_ai_repair,
    can_run_check,
    check_permission,
    classify_check,
    record_successful_check,
    remaining_ai_rechecks,
)


@pytest.mark.parametrize("edit_source", [None, AI_REPAIR, MANUAL])
def test_first_check_does_not_depend_on_edit_source(edit_source):
    assert (
        classify_check(
            has_previous_check=False,
            pending_edit_source=edit_source,
        )
        == INITIAL
    )


def test_check_kind_is_determined_by_last_edit_source():
    assert classify_check(has_previous_check=True, pending_edit_source=AI_REPAIR) == AI_RECHECK
    assert classify_check(has_previous_check=True, pending_edit_source=MANUAL) == MANUAL_FINAL


def test_checked_but_unedited_card_cannot_be_classified_for_recheck():
    with pytest.raises(ValueError, match="수정되지 않은 카드"):
        classify_check(has_previous_check=True, pending_edit_source=None)


@pytest.mark.parametrize(
    ("count", "remaining", "can_apply"),
    [(0, 2, True), (1, 1, True), (2, 0, False), (3, 0, False)],
)
def test_ai_recheck_limit(count, remaining, can_apply):
    assert remaining_ai_rechecks(count) == remaining
    assert can_apply_ai_repair(count) is can_apply


def test_initial_check_is_allowed_and_does_not_change_counters():
    assert can_run_check(
        check_kind=INITIAL,
        ai_recheck_count=0,
        manual_final_check_used=False,
    )
    assert record_successful_check(
        check_kind=INITIAL,
        ai_recheck_count=0,
        manual_final_check_used=False,
    ) == (0, False)


def test_successful_ai_recheck_increments_only_ai_count():
    assert record_successful_check(
        check_kind=AI_RECHECK,
        ai_recheck_count=1,
        manual_final_check_used=False,
    ) == (MAX_AI_RECHECKS, False)


def test_third_ai_recheck_is_blocked():
    permission = check_permission(
        check_kind=AI_RECHECK,
        ai_recheck_count=MAX_AI_RECHECKS,
        manual_final_check_used=False,
    )

    assert not permission.allowed
    assert permission.reason == AI_RECHECK_LIMIT_REACHED
    with pytest.raises(ValueError, match=AI_RECHECK_LIMIT_REACHED):
        record_successful_check(
            check_kind=AI_RECHECK,
            ai_recheck_count=MAX_AI_RECHECKS,
            manual_final_check_used=False,
        )


def test_manual_final_check_is_separate_from_ai_recheck_count():
    assert record_successful_check(
        check_kind=MANUAL_FINAL,
        ai_recheck_count=MAX_AI_RECHECKS,
        manual_final_check_used=False,
    ) == (MAX_AI_RECHECKS, True)


def test_second_manual_final_check_is_blocked():
    permission = check_permission(
        check_kind=MANUAL_FINAL,
        ai_recheck_count=0,
        manual_final_check_used=True,
    )

    assert not permission.allowed
    assert permission.reason == MANUAL_FINAL_CHECK_USED


@pytest.mark.parametrize("invalid_count", [-1, 1.5, True])
def test_invalid_ai_recheck_count_is_rejected(invalid_count):
    with pytest.raises((TypeError, ValueError)):
        remaining_ai_rechecks(invalid_count)
