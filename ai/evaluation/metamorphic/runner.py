import argparse
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

from ai.evaluation.metamorphic.metrics import (
    evaluate_case,
    get_completeness_status,
    get_factuality_status,
    summarize_results,
)
from ai.evaluation.metamorphic.mutations import (
    CASES,
    mutate_cards,
)
from ai.verification.completeness.llm.llm_checker import check_llm_completeness
from ai.verification.factuality.llm.llm_checker import check_llm_factuality
from data_pipeline.schemas.card import FinalCardOutput
from data_pipeline.schemas.group import Group

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "data" / "samples"
RESULTS = ROOT / "data" / "evaluation" / "metamorphic"


def to_jsonable(obj):
    if isinstance(obj, Enum):
        return to_jsonable(obj.value)

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, dict):
        return {str(key): to_jsonable(value) for key, value in obj.items()}

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(value) for value in obj]

    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump(mode="json"))

    if is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: to_jsonable(getattr(obj, field.name)) for field in fields(obj)}

    if hasattr(obj, "__dict__"):
        return {
            key: to_jsonable(value) for key, value in vars(obj).items() if not key.startswith("_")
        }

    raise TypeError(f"JSON 직렬화 불가: {type(obj).__name__}")


def load_json(path):
    if not path.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            to_jsonable(data),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def build_final_cards(cards_data):
    body_cards = []

    for index, card in enumerate(cards_data["cards"], start=1):
        if card["layout_id"] in ("cover", "closing"):
            continue

        if card.get("group_id") is None:
            raise ValueError("본문 카드에 group_id가 없습니다.")

        body_cards.append(
            {
                **card,
                "card_id": card.get("card_id") or f"C{index}",
            }
        )

    return FinalCardOutput.model_validate(
        {
            "document_id": cards_data["document_id"],
            "cards": body_cards,
        }
    )


def get_target_card_id(cards_data, group_id):
    for index, card in enumerate(cards_data["cards"], start=1):
        if card.get("group_id") == group_id:
            return card.get("card_id") or f"C{index}"

    raise ValueError(f"그룹에 연결된 카드를 찾지 못했습니다: {group_id}")


def validate_documents(analysis, original, baseline):
    document_ids = {
        analysis["document_id"],
        original["document_id"],
        baseline["document_id"],
    }

    if len(document_ids) != 1:
        raise ValueError("분석, 카드, baseline의 document_id가 일치하지 않습니다.")

    if not baseline.get("factuality"):
        raise ValueError("baseline에 사실성 결과가 없습니다.")

    if not baseline.get("completeness"):
        raise ValueError("baseline에 완전성 결과가 없습니다.")


def run_case(case, groups, original, baseline):
    mutated, mutation = mutate_cards(original, case)

    final_cards = build_final_cards(mutated)

    entry = {
        "case_id": case["id"],
        "name": case["name"],
        "type": case["type"],
        "group_id": case["group_id"],
        "target": case["target"],
        "mutation": mutation,
    }

    if case["type"] == "factuality":
        card_id = get_target_card_id(
            original,
            case["group_id"],
        )

        baseline_status = get_factuality_status(
            baseline["factuality"],
            card_id,
            case["target"],
        )

        response = check_llm_factuality(
            groups=groups,
            final_cards=final_cards,
        )

        verification = to_jsonable(response)

        actual_status = get_factuality_status(
            verification,
            card_id,
            case["target"],
        )

    else:
        baseline_status = get_completeness_status(
            baseline["completeness"],
            case["group_id"],
        )

        response = check_llm_completeness(
            groups=groups,
            final_cards=final_cards,
            required_group_ids=[group.group_id for group in groups],
        )

        verification = to_jsonable(response)

        actual_status = get_completeness_status(
            verification,
            case["group_id"],
        )

    entry.update(
        evaluate_case(
            case,
            baseline_status,
            actual_status,
        )
    )

    entry["verification"] = verification

    return entry


def run(document_id="news_014", rerun=False):
    analysis_path = SAMPLES / f"{document_id}_analysis.json"
    cards_path = SAMPLES / f"{document_id}_cards.json"
    baseline_path = SAMPLES / f"{document_id}_baseline.json"
    output_path = RESULTS / f"{document_id}_results.json"

    analysis = load_json(analysis_path)
    original = load_json(cards_path)
    baseline = load_json(baseline_path)

    validate_documents(analysis, original, baseline)

    groups = [Group.model_validate(group) for group in analysis["groups"]]

    selected_cases = CASES

    if document_id != "news_014":
        raise ValueError(
            "현재 변형 사례는 news_014 전용입니다. "
            "다른 기사에는 별도의 변형 사례 정의가 필요합니다."
        )

    if output_path.is_file() and not rerun:
        results = load_json(output_path)
    else:
        results = {
            "document_id": document_id,
            "evaluation_type": "metamorphic",
            "cases": [],
        }

    completed_ids = {
        item["case_id"] for item in results["cases"] if isinstance(item.get("mr_satisfied"), bool)
    }

    print(f"문서 ID: {document_id}")
    print(f"변형 사례 수: {len(selected_cases)}")

    for case in selected_cases:
        if case["id"] in completed_ids:
            print(f"[{case['id']}] 완료된 사례 건너뜀")
            continue

        print(f"\n[{case['id']}] {case['name']} 실행")

        try:
            entry = run_case(
                case,
                groups,
                original,
                baseline,
            )

            print(f"원본: {entry['baseline_status']} → 변형: {entry['actual_status']}")
            print(f"MR 충족: {entry['mr_satisfied']}")

        except Exception as error:
            entry = {
                "case_id": case["id"],
                "name": case["name"],
                "type": case["type"],
                "group_id": case["group_id"],
                "target": case["target"],
                "mr_satisfied": None,
                "error": (f"{type(error).__name__}: {error}"),
            }

            print(f"실행 실패: {entry['error']}")

        results["cases"] = [item for item in results["cases"] if item["case_id"] != case["id"]]

        results["cases"].append(entry)
        results["summary"] = summarize_results(results["cases"])

        save_json(output_path, results)

    results["summary"] = summarize_results(results["cases"])

    save_json(output_path, results)

    print("\n=== 최종 결과 ===")
    print(
        json.dumps(
            results["summary"],
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\n결과 저장: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--document",
        default="news_014",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
    )

    args = parser.parse_args()

    run(
        document_id=args.document,
        rerun=args.rerun,
    )


if __name__ == "__main__":
    main()
