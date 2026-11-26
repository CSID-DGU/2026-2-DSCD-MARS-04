def get_factuality_status(result, card_id, field_path):
    matches = [
        field
        for card in result.get("cards", [])
        if card["card_id"] == card_id
        for field in card.get("fields", [])
        if field["field_path"] == field_path
    ]

    if len(matches) != 1:
        raise ValueError(f"사실성 판정을 찾을 수 없습니다: {card_id}:{field_path}")

    return matches[0]["status"]


def get_completeness_status(result, group_id):
    fact_id = f"{group_id}:summary"

    matches = [item for item in result.get("results", []) if item["fact_id"] == fact_id]

    if len(matches) != 1:
        raise ValueError(f"완전성 판정을 찾을 수 없습니다: {fact_id}")

    return matches[0]["status"]


def evaluate_case(case, baseline_status, actual_status):
    expected = case["expected"]

    satisfied = actual_status in expected

    return {
        "baseline_status": baseline_status,
        "actual_status": actual_status,
        "expected_statuses": expected,
        "status_changed": baseline_status != actual_status,
        "mr_satisfied": satisfied,
    }


def summarize_results(cases):
    completed = [case for case in cases if isinstance(case.get("mr_satisfied"), bool)]

    passed = [case for case in completed if case["mr_satisfied"]]

    failed = [case for case in cases if case.get("error") is not None]

    summary = {
        "total_cases": len(cases),
        "completed_cases": len(completed),
        "passed_cases": len(passed),
        "failed_execution_cases": len(failed),
        "mr_satisfaction_rate": (round(len(passed) / len(completed), 4) if completed else None),
        "by_type": {},
    }

    for test_type in ("factuality", "completeness"):
        subset = [case for case in completed if case["type"] == test_type]

        passed_count = sum(case["mr_satisfied"] for case in subset)

        summary["by_type"][test_type] = {
            "completed": len(subset),
            "passed": passed_count,
            "mr_satisfaction_rate": (round(passed_count / len(subset), 4) if subset else None),
        }

    return summary
