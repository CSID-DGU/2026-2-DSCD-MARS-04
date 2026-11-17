import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from openai import OpenAI

from ai.evaluation.ablation.metrics import (
    METRIC_KEYS,
    NORMAL_STATUS,
    evaluate_ablation_case,
    summarize_scores,
)
from ai.evaluation.metamorphic.metrics import (
    get_completeness_status,
    get_factuality_status,
)
from ai.evaluation.metamorphic.mutations import CASES, mutate_cards
from ai.evaluation.metamorphic.runner import (
    ROOT,
    SAMPLES,
    build_final_cards,
    get_target_card_id,
    load_json,
    save_json,
    to_jsonable,
)
from ai.verification.completeness.llm.llm_checker import (
    check_llm_completeness,
    load_completeness_prompt,
)
from ai.verification.factuality.llm.llm_checker import (
    check_llm_factuality,
    load_verification_prompt,
)
from ai.verification.shared.card_text_extractor import extract_card_texts
from data_pipeline.schemas.group import Group

MODEL = "gpt-4.1-mini"
PROMPT_DIR = Path(__file__).with_name("prompts")
VARIANT_NAMES = ("Basic", "Full", "Concise")


class MeasuredClient:
    def __init__(self, client, instructions):
        self.client = client
        self.instructions = instructions
        self.responses = self
        self.usage = Counter(calls=0, input_tokens=0, output_tokens=0)

    def parse(self, **kwargs):
        kwargs["instructions"] = self.instructions
        self.usage["calls"] += 1
        response = self.client.responses.parse(**kwargs)

        if response.usage is not None:
            self.usage.update(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return response


def load_prompt(path):
    if not path.is_file():
        raise FileNotFoundError(f"프롬프트 파일이 없습니다: {path}")

    prompt = path.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError(f"프롬프트가 비어 있습니다: {path}")

    return prompt


def load_prompt_variants():
    return {
        "Basic": {
            "factuality": load_prompt(PROMPT_DIR / "factuality_basic.md"),
            "completeness": load_prompt(PROMPT_DIR / "completeness_basic.md"),
        },
        "Full": {
            "factuality": load_verification_prompt(),
            "completeness": load_completeness_prompt(),
        },
        "Concise": {
            "factuality": load_prompt(PROMPT_DIR / "factuality_concise.md"),
            "completeness": load_prompt(PROMPT_DIR / "completeness_concise.md"),
        },
    }


def build_jobs(original):
    original_cards = build_final_cards(original)

    for kind in NORMAL_STATUS:
        yield kind, None, original_cards

    for case in CASES:
        mutated, mutation = mutate_cards(original, case)
        yield case["type"], {**case, "mutation": mutation}, build_final_cards(mutated)


def count_calls(kind, cards):
    if kind == "factuality":
        return len({unit.card_id for unit in extract_card_texts(cards)})

    return len({card.group_id for card in cards.cards})


def get_case_status(kind, verification, case, original):
    if kind == "completeness":
        return get_completeness_status(verification, case["group_id"])

    return get_factuality_status(
        verification,
        get_target_card_id(original, case["group_id"]),
        case["target"],
    )


def verify(kind, groups, cards, client):
    common = {
        "groups": groups,
        "final_cards": cards,
        "model": MODEL,
        "client": client,
    }

    if kind == "factuality":
        return check_llm_factuality(**common)

    return check_llm_completeness(
        **common,
        required_group_ids=[group.group_id for group in groups],
    )


def create_output_path(document_id):
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return ROOT / "data/evaluation/ablation" / f"{document_id}_{timestamp}.json"


def print_plan(document_id, calls_per_variant):
    total_calls = calls_per_variant * len(VARIANT_NAMES)
    print(f"문서 ID: {document_id}")
    print(f"모델: {MODEL}")
    print(f"프롬프트: {', '.join(VARIANT_NAMES)}")
    print(f"예상 호출: {calls_per_variant}회 × 3종 = {total_calls}회")


def print_summary(results, output_path):
    print("\nVariant   Match  Detect  Retain  MR    Input  Output  Seconds")

    for name in VARIANT_NAMES:
        summary = results["variants"][name]["summary"]
        ratios = "  ".join(
            f"{summary[key]['passed']}/{summary[key]['total']}" for key in METRIC_KEYS
        )
        print(
            f"{name:8}  {ratios}  {summary['input_tokens']}  "
            f"{summary['output_tokens']}  {summary['seconds']:.2f}"
        )

    print(f"\n결과 저장: {output_path}")


def run(document_id="news_014", execute=False, output_path=None):
    if document_id != "news_014":
        raise ValueError("현재 ablation 평가는 news_014 전용입니다.")

    original = load_json(SAMPLES / f"{document_id}_cards.json")
    analysis = load_json(SAMPLES / f"{document_id}_analysis.json")

    if original["document_id"] != analysis["document_id"]:
        raise ValueError("분석과 카드의 document_id가 일치하지 않습니다.")

    groups = [Group.model_validate(item) for item in analysis["groups"]]
    prompt_variants = load_prompt_variants()
    jobs = list(build_jobs(original))
    calls_per_variant = sum(count_calls(kind, cards) for kind, _, cards in jobs)
    print_plan(document_id, calls_per_variant)

    if not execute:
        return None

    output_path = output_path or create_output_path(document_id)

    if output_path.exists():
        raise FileExistsError(f"결과 파일이 이미 존재합니다: {output_path}")

    results = {
        "document_id": document_id,
        "evaluation_type": "prompt_ablation",
        "model": MODEL,
        "variants": {},
    }
    client = OpenAI(max_retries=0)

    for variant_name in VARIANT_NAMES:
        baseline = {}
        records = []
        scores = []
        totals = Counter(calls=0, input_tokens=0, output_tokens=0)
        results["variants"][variant_name] = {"records": records}

        for kind, case, cards in jobs:
            measured_client = MeasuredClient(client, prompt_variants[variant_name][kind])
            record = {
                "case_id": case["id"] if case else "original",
                "type": kind,
            }

            if case:
                record["mutation"] = case["mutation"]

            started_at = perf_counter()

            try:
                response = verify(kind, groups, cards, measured_client)
                verification = to_jsonable(response)
                record["verification"] = verification

                if case is None:
                    baseline[kind] = verification
                else:
                    baseline_status = get_case_status(kind, baseline[kind], case, original)
                    actual_status = get_case_status(kind, verification, case, original)
                    record["metrics"] = evaluate_ablation_case(case, baseline_status, actual_status)
                    scores.append(record["metrics"])
            except Exception as error:
                record["error"] = f"{type(error).__name__}: {error}"
                raise
            finally:
                elapsed = perf_counter() - started_at
                usage = dict(measured_client.usage)
                record["usage"] = {**usage, "seconds": elapsed}
                totals.update(usage)
                totals["seconds"] += elapsed
                records.append(record)
                save_json(output_path, results)

        results["variants"][variant_name]["summary"] = {
            **summarize_scores(scores),
            **totals,
        }
        save_json(output_path, results)

    print_summary(results, output_path)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", default="news_014")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run(args.document, args.execute, args.output)


if __name__ == "__main__":
    main()
