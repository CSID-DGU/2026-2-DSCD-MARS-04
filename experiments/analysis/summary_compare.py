"""요약 모델 비교 실험: 같은 그룹 + 같은 길이 목표에서 모델만 바꿔 비교한다.

실행 (레포 맨 위 폴더에서):
  시험 실행: python -m experiments.analysis.summary_compare --n 2
  본 실험:   python -m experiments.analysis.summary_compare --n 20
  같은 그룹 재사용: --groups-file experiments/analysis/results/<폴더>/fixed_groups.json
"""

import argparse
import json
import re
from pathlib import Path

from dotenv import load_dotenv

from ai.analysis import summarizer
from ai.analysis.grouper import ROOT
from ai.analysis.summarizer import SummaryResult, build_summary_input, check_summaries
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
from experiments.analysis.group_compare import run_grouping

LENGTH_RULE = """

# 길이 목표
각 그룹의 요약은 그룹 원문 글자 수의 {target}% 이내를 목표로 합니다.
길이를 맞추기 위해 숫자, 한정 표현, 조건, 출처 표현을 지우지 않습니다."""

# 요약에서 지켜졌는지 셀 한정·조건 표현 (근사치용)
QUALIFIERS = ["최대", "최소", "약 ", "이상", "이하", "미만", "초과", " 등", "단,", "다만", "제외"]


def make_prompt(target):
    base = summarizer.PROMPT_PATH.read_text(encoding="utf-8").strip()
    return base if target == "none" else base + LENGTH_RULE.format(target=target)


def run_summary(model, prompt, sentences, groups):
    """레포와 같은 규칙: 숫자 검사 → 걸린 그룹만 1회 재요청 → 원문 대체."""
    text = {s["sentence_id"]: s["text"] for s in sentences}
    usage = {}

    parsed = call_model(model, prompt, build_summary_input(sentences, groups), SummaryResult, usage)
    summaries = {item.group_id: item.summary for item in parsed.summaries}
    first_summaries = dict(summaries)
    errors = check_summaries(sentences, groups, summaries)
    retried = list(errors)

    if errors:
        failed = [g for g in groups if g["group_id"] in errors]
        parsed = call_model(
            model, prompt, build_summary_input(sentences, failed, errors), SummaryResult, usage
        )
        for item in parsed.summaries:
            if item.group_id in errors:
                summaries[item.group_id] = item.summary
        errors = check_summaries(sentences, failed, summaries)

    for group_id in errors:
        group = next(g for g in groups if g["group_id"] == group_id)
        summaries[group_id] = " ".join(text[i] for i in group["sentence_ids"])

    return {
        "summaries": summaries,
        "first_summaries": first_summaries,
        "retried_group_ids": retried,
        "fallback_group_ids": list(errors),
        "usage": usage,
    }


# ── 지표 ─────────────────────────────────────────────────────


def words(text):
    return [w for w in re.sub(r"[^\w%.]", " ", text).split() if w]


def summary_metrics(sentences, groups, result):
    """원문 대체된 그룹은 빼고, 그룹마다 길이 비율·원문 어절 비율·한정 표현 보존을 센다."""
    text = {s["sentence_id"]: s["text"] for s in sentences}
    length_ratios, word_ratios = [], []
    q_total = q_kept = 0
    for group in groups:
        if group["group_id"] in result["fallback_group_ids"]:
            continue
        source = " ".join(text[i] for i in group["sentence_ids"])
        summary = result["summaries"].get(group["group_id"], "")
        length_ratios.append(len(summary) / len(source))
        source_words, summary_words = set(words(source)), words(summary)
        if summary_words:
            word_ratios.append(sum(w in source_words for w in summary_words) / len(summary_words))
        for q in QUALIFIERS:
            q_total += source.count(q)
            q_kept += min(source.count(q), summary.count(q))
    return {
        "group_count": len(groups),
        "retried_count": len(result["retried_group_ids"]),
        "fallback_count": len(result["fallback_group_ids"]),
        "length_ratios": length_ratios,
        "word_ratios": word_ratios,
        "qualifier_total": q_total,
        "qualifier_kept": q_kept,
    }


def summarize_condition(model, target, records):
    ok = [r for r in records if "api_error" not in r]
    metrics = [r["summary_metrics"] for r in ok]
    groups_total = sum(m["group_count"] for m in metrics)
    ratios = [x for m in metrics for x in m["length_ratios"]]
    hit = None
    if target != "none" and ratios:
        hit = rate(sum(x <= int(target) / 100 + 0.05 for x in ratios), len(ratios))

    tokens_in = sum(r["summary"]["usage"]["input_tokens"] for r in ok)
    tokens_out = sum(r["summary"]["usage"]["output_tokens"] for r in ok)
    return {
        "model": model,
        "target": target,
        "articles": len(records),
        "api_errors": len(records) - len(ok),
        "length_ratio": mean(ratios),
        "target_hit": hit,
        "number_miss_first": rate(sum(m["retried_count"] for m in metrics), groups_total),
        "fallback": rate(sum(m["fallback_count"] for m in metrics), groups_total),
        "qualifier_kept": rate(
            sum(m["qualifier_kept"] for m in metrics), sum(m["qualifier_total"] for m in metrics)
        ),
        "source_word_ratio": mean(x for m in metrics for x in m["word_ratios"]),
        "latency_s": mean((r["summary"]["usage"]["latency_seconds"] for r in ok), 2),
        "cost_per_article_usd": cost_per_article(model, tokens_in, tokens_out, len(ok)),
    }


# ── 실행 ─────────────────────────────────────────────────────


def load_fixed_groups(articles, groups_file, group_model, run_dir):
    """기사마다 기준 모델로 그룹을 한 번만 만든다. 파일이 있으면 그대로 다시 쓴다."""
    if groups_file:
        return json.loads(Path(groups_file).read_text(encoding="utf-8"))
    fixed = {}
    for index, article in enumerate(articles, 1):
        result = run_grouping(group_model, article["sentences"])
        if result["valid"]:
            fixed[article["document_id"]] = result["groups"]
        print(f"\r기준 그룹 만들기 {index}/{len(articles)}", end="", flush=True)
    print()
    (run_dir / "fixed_groups.json").write_text(
        json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return fixed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/samples/original_text.xlsx")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument(
        "--models", nargs="+", default=["gpt-4.1-mini@0", "gpt-6-luna@0", "claude-haiku-5-5"]
    )
    parser.add_argument("--targets", nargs="+", default=["none", "70", "50"], help="none 70 50")
    parser.add_argument("--group-model", default="gpt-4.1-mini@0")
    parser.add_argument("--groups-file", help="이전 실행의 fixed_groups.json")
    args = parser.parse_args()
    for spec in args.models + [args.group_model]:
        parse_spec(spec)

    load_dotenv(ROOT / ".env")
    articles = pick_articles(args.file, args.n)
    run_dir = make_run_dir("summary")

    fixed = load_fixed_groups(articles, args.groups_file, args.group_model, run_dir)
    articles = [a for a in articles if a["document_id"] in fixed]
    conditions = [(m, t) for m in args.models for t in args.targets]
    total = len(conditions) * len(articles)
    sizes = f"기사 {len(articles)}개 × 모델 {len(args.models)}개 × 길이 목표 {len(args.targets)}개"
    print(f"{sizes} = {total}회")

    rows, done = [], 0
    with (run_dir / "raw.jsonl").open("w", encoding="utf-8") as raw:
        for model, target in conditions:
            prompt = make_prompt(target)
            records = []
            for article in articles:
                sentences = article["sentences"]
                groups = fixed[article["document_id"]]
                record = {"model": model, "target": target, "document_id": article["document_id"]}
                try:
                    record["summary"] = run_summary(model, prompt, sentences, groups)
                    record["summary_metrics"] = summary_metrics(
                        sentences, groups, record["summary"]
                    )
                except Exception as error:  # noqa: BLE001
                    record["api_error"] = f"{type(error).__name__}: {error}"
                records.append(record)
                raw.write(json.dumps(record, ensure_ascii=False) + "\n")
                raw.flush()
                done += 1
                print(f"\r진행 {done}/{total} ({model}, {target})", end="", flush=True)
            rows.append(summarize_condition(model, target, records))
    print()

    config = {**vars(args), "document_ids": [a["document_id"] for a in articles]}
    save_results(run_dir, rows, config)


if __name__ == "__main__":
    main()
