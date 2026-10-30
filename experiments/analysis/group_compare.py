"""그룹화 모델 비교: 같은 기사를 모델마다 여러 번 그룹화해 일관성(ARI)과 통과율을 비교한다.

실행
  시험 실행: python -m experiments.analysis.group_compare --n 2 --repeat 1
  본 실험:   python -m experiments.analysis.group_compare --n 20 --repeat 3
"""

import argparse
import json
import statistics
from itertools import combinations

from dotenv import load_dotenv
from sklearn.metrics import adjusted_rand_score

from ai.analysis import grouper
from ai.analysis.grouper import MAX_GROUPS, ROOT, GroupingResult, check_grouping, order_groups
from experiments.analysis.common import (
    call_model,
    cost_per_article,
    make_run_dir,
    mean,
    parse_spec,
    pick_articles,
    rate,
    save_results,
)


def run_grouping(model, sentences, max_groups=MAX_GROUPS):
    """레포와 같은 규칙: 검사 → 1회 재요청 → 정렬."""
    prompt = grouper.PROMPT_PATH.read_text(encoding="utf-8").strip()
    sentence_ids = [s["sentence_id"] for s in sentences]
    usage, errors, groups, first_try_valid = {}, [], [], False

    for attempt in (1, 2):
        payload = {"max_groups": max_groups, "sentences": sentences}
        if errors:
            payload["previous_errors"] = errors
        parsed = call_model(
            model, prompt, json.dumps(payload, ensure_ascii=False), GroupingResult, usage
        )
        groups = [g.model_dump() for g in parsed.groups]
        errors = check_grouping(sentence_ids, groups)
        if attempt == 1:
            first_try_valid = not errors
        if not errors:
            groups = order_groups(groups, sentence_ids)
            break

    return {
        "groups": groups,
        "valid": not errors,
        "errors": errors,
        "first_try_valid": first_try_valid,
        "over_max_groups": len(groups) > max_groups,
        "usage": usage,
    }


def to_labels(sentence_ids, groups):
    label = {sid: n for n, g in enumerate(groups) for sid in g["sentence_ids"]}
    return [label.get(sid, -1) for sid in sentence_ids]


def summarize_model(model, records, repeat):
    ok = [r for r in records if "api_error" not in r]
    grouped = [r for r in ok if r["grouping"]["valid"]]

    ari_scores = []
    for document_id in {r["document_id"] for r in grouped}:
        runs = [r for r in grouped if r["document_id"] == document_id]
        if len(runs) == repeat and repeat > 1:
            labels = [to_labels(runs[0]["sentence_ids"], r["grouping"]["groups"]) for r in runs]
            ari_scores.append(
                statistics.mean(adjusted_rand_score(a, b) for a, b in combinations(labels, 2))
            )

    tokens_in = sum(r["grouping"]["usage"]["input_tokens"] for r in ok)
    tokens_out = sum(r["grouping"]["usage"]["output_tokens"] for r in ok)
    return {
        "model": model,
        "runs": len(records),
        "api_errors": len(records) - len(ok),
        "first_try_pass": rate(sum(r["grouping"]["first_try_valid"] for r in ok), len(ok)),
        "final_pass": rate(len(grouped), len(ok)),
        "ari": mean(ari_scores),
        "ari_articles": len(ari_scores),
        "mean_group_count": mean(len(r["grouping"]["groups"]) for r in grouped),
        "sentences_per_group": mean(
            len(r["sentence_ids"]) / len(r["grouping"]["groups"]) for r in grouped
        ),
        "over_max": rate(sum(r["grouping"]["over_max_groups"] for r in grouped), len(grouped)),
        "latency_s": mean((r["grouping"]["usage"]["latency_seconds"] for r in ok), 2),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_per_run_usd": cost_per_article(model, tokens_in, tokens_out, len(ok)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/samples/original_text.xlsx")
    parser.add_argument("--n", type=int, default=20, help="기사 수")
    parser.add_argument("--repeat", type=int, default=3, help="기사마다 반복 횟수")
    parser.add_argument(
        "--models", nargs="+", default=["gpt-4.1-mini@0", "gpt-6-luna@0", "claude-haiku-5-5"]
    )
    args = parser.parse_args()
    for spec in args.models:
        parse_spec(spec)

    load_dotenv(ROOT / ".env")
    articles = pick_articles(args.file, args.n)
    run_dir = make_run_dir("group")
    total = len(articles) * args.repeat * len(args.models)
    print(f"기사 {len(articles)}개 × 반복 {args.repeat}회 × 모델 {len(args.models)}개 = {total}회")

    rows, done = [], 0
    with (run_dir / "raw.jsonl").open("w", encoding="utf-8") as raw:
        for model in args.models:
            records = []
            for article in articles:
                sentence_ids = [s["sentence_id"] for s in article["sentences"]]
                for run in range(1, args.repeat + 1):
                    record = {
                        "model": model,
                        "document_id": article["document_id"],
                        "run": run,
                        "sentence_ids": sentence_ids,
                    }
                    try:
                        record["grouping"] = run_grouping(model, article["sentences"])
                    except Exception as error:  # noqa: BLE001
                        record["api_error"] = f"{type(error).__name__}: {error}"
                    records.append(record)
                    raw.write(json.dumps(record, ensure_ascii=False) + "\n")
                    raw.flush()
                    done += 1
                    print(f"\r진행 {done}/{total} ({model})", end="", flush=True)
            rows.append(summarize_model(model, records, args.repeat))
    print()

    config = {**vars(args), "document_ids": [a["document_id"] for a in articles]}
    save_results(run_dir, rows, config)


if __name__ == "__main__":
    main()
