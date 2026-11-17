from ai.evaluation.metamorphic.metrics import evaluate_case

NORMAL_STATUS = {
    "factuality": "SUPPORTED",
    "completeness": "COVERED",
}

ERROR_STATUSES = {
    "factuality": {"POSSIBLE_DISTORTION", "INSUFFICIENT_EVIDENCE"},
    "completeness": {"PARTIALLY_COVERED", "MISSING", "DISTORTED"},
}

METRIC_KEYS = (
    "expected_match",
    "error_detected",
    "normal_retained",
    "mr_satisfied",
)


def evaluate_ablation_case(case, baseline_status, actual_status):
    evaluation = evaluate_case(case, baseline_status, actual_status)
    kind = case["type"]
    expected_match = evaluation["mr_satisfied"]
    is_normal_case = NORMAL_STATUS[kind] in case["expected"]

    return {
        **evaluation,
        "expected_match": expected_match,
        "error_detected": None if is_normal_case else actual_status in ERROR_STATUSES[kind],
        "normal_retained": (
            baseline_status == actual_status == NORMAL_STATUS[kind] if is_normal_case else None
        ),
        "mr_satisfied": baseline_status == NORMAL_STATUS[kind] and expected_match,
    }


def calculate_rate(values):
    observed = [value for value in values if value is not None]

    return {
        "passed": sum(observed),
        "total": len(observed),
        "rate": round(sum(observed) / len(observed), 4) if observed else None,
    }


def summarize_scores(scores):
    return {key: calculate_rate(score[key] for score in scores) for key in METRIC_KEYS}
