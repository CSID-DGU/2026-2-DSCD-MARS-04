import argparse
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from ai.analysis.grouper import DEFAULT_MODEL, DEFAULT_TEMPERATURE, ROOT, group_sentences
from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.sentence_splitter import split_sentences

PROMPT_PATH = Path(__file__).with_name("prompts") / "summary.md"
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


class GroupSummary(BaseModel):
    group_id: str
    summary: str


class SummaryResult(BaseModel):
    summaries: list[GroupSummary]


def build_summary_input(
    sentences: list[dict], groups: list[dict], previous_errors: dict[str, str] | None = None
) -> str:
    by_id = {sentence["sentence_id"]: sentence for sentence in sentences}
    position = {sentence["sentence_id"]: index for index, sentence in enumerate(sentences)}

    items = []
    for group in groups:
        first = position[group["sentence_ids"][0]]
        item = {
            "group_id": group["group_id"],
            "sentences": [by_id[i] for i in group["sentence_ids"]],
            "previous_sentence": sentences[first - 1]["text"] if first > 0 else None,
        }
        if previous_errors and group["group_id"] in previous_errors:
            item["previous_error"] = previous_errors[group["group_id"]]
        items.append(item)
    return json.dumps({"groups": items}, ensure_ascii=False)


def call_summary(
    sentences: list[dict],
    groups: list[dict],
    *,
    previous_errors: dict[str, str] | None = None,
    model: str | None = None,
    client: OpenAI | None = None,
) -> dict:
    load_dotenv(ROOT / ".env")
    model = model or os.getenv("ANALYSIS_MODEL", DEFAULT_MODEL)
    client = client or OpenAI()

    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    user_input = build_summary_input(sentences, groups, previous_errors)

    started = time.perf_counter()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        text_format=SummaryResult,
        temperature=DEFAULT_TEMPERATURE,
    )
    latency = time.perf_counter() - started

    if response.output_parsed is None:
        raise RuntimeError("스키마에 맞는 요약 결과가 없습니다.")

    return {
        "summaries": [item.model_dump() for item in response.output_parsed.summaries],
        "model": model,
        "response_model": getattr(response, "model", None),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_seconds": round(latency, 2),
    }


def find_missing_numbers(source: str, summary: str) -> list[str]:
    """원문에 있는데 요약에 없는 숫자. 1,000과 1000은 같은 숫자로 본다."""

    def numbers(text: str) -> list[str]:
        return [n.replace(",", "") for n in NUMBER.findall(text)]

    kept = set(numbers(summary))
    return sorted(set(numbers(source)) - kept, key=numbers(source).index)


def number_context(number: str, source: str) -> str:
    for word in source.split():
        if number in [n.replace(",", "") for n in NUMBER.findall(word)]:
            return word
    return number


def check_summaries(sentences: list[dict], groups: list[dict], summaries: dict) -> dict:
    """그룹마다 문제를 찾는다. 문제가 없는 그룹은 결과에 없다."""
    text = {s["sentence_id"]: s["text"] for s in sentences}
    errors = {}
    for group in groups:
        summary = summaries.get(group["group_id"], "").strip()
        if not summary:
            errors[group["group_id"]] = "요약이 비어 있습니다."
            continue
        source = " ".join(text[i] for i in group["sentence_ids"])
        missing = find_missing_numbers(source, summary)
        if missing:
            where = ", ".join(f"'{number_context(n, source)}'의 {n}" for n in missing)
            errors[group["group_id"]] = (
                f"원문의 숫자가 빠졌습니다: {where}. 이 숫자를 요약에 남기세요."
            )
    return errors


def summarize_groups(
    sentences: list[dict],
    groups: list[dict],
    *,
    model: str | None = None,
    client: OpenAI | None = None,
    max_retries: int = 1,
) -> dict:
    """요약하고 검사한다. 걸린 그룹만 다시 요청하고, 그래도 안 되면 원문 문장으로 대체한다."""
    text = {s["sentence_id"]: s["text"] for s in sentences}
    first = call_summary(sentences, groups, model=model, client=client)
    summaries = {item["group_id"]: item["summary"] for item in first["summaries"]}
    errors = check_summaries(sentences, groups, summaries)
    group_ids = [g["group_id"] for g in groups]
    calls = [{"attempt": 1, "group_ids": group_ids, **first, "errors": errors}]
    retried = list(errors)

    for attempt in range(2, max_retries + 2):
        if not errors:
            break
        failed = [g for g in groups if g["group_id"] in errors]
        result = call_summary(sentences, failed, previous_errors=errors, model=model, client=client)
        for item in result["summaries"]:
            if item["group_id"] in errors:
                summaries[item["group_id"]] = item["summary"]
        errors = check_summaries(sentences, failed, summaries)
        calls.append(
            {
                "attempt": attempt,
                "group_ids": [g["group_id"] for g in failed],
                **result,
                "errors": errors,
            }
        )

    for group_id in errors:
        group = next(g for g in groups if g["group_id"] == group_id)
        summaries[group_id] = " ".join(text[i] for i in group["sentence_ids"])

    return {
        "groups": [{**group, "summary": summaries[group["group_id"]]} for group in groups],
        "retried_group_ids": retried,
        "fallback_group_ids": list(errors),
        "fallback_reasons": errors,
        "attempts": len(calls),
        "model": calls[-1]["model"],
        "response_model": calls[-1]["response_model"],
        "max_retries": max_retries,
        "temperature": DEFAULT_TEMPERATURE,
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "latency_seconds": round(sum(c["latency_seconds"] for c in calls), 2),
        "calls": calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="기사 하나를 그룹화하고 요약해 본다")
    parser.add_argument("--file", default="data/samples/original_text.xlsx")
    parser.add_argument("--index", type=int, default=0, help="몇 번째 기사 (0부터)")
    args = parser.parse_args()

    article = load_articles(args.file, limit=args.index + 1)[args.index]
    sentences = split_sentences(article["source_text"])
    grouping = group_sentences(sentences)
    if not grouping["valid"]:
        print("그룹화 실패:", grouping["errors"])
        return

    result = summarize_groups(sentences, grouping["groups"])
    text = {s["sentence_id"]: s["text"] for s in sentences}

    for group in result["groups"]:
        mark = " (원문으로 대체)" if group["group_id"] in result["fallback_group_ids"] else ""
        print(f"\n[{group['group_id']}] {', '.join(group['sentence_ids'])}{mark}")
        for sentence_id in group["sentence_ids"]:
            print(f"  원문 {sentence_id}: {text[sentence_id]}")
        print(f"  요약: {group['summary']}")

    keys = ("retried_group_ids", "fallback_reasons", "attempts", "model")
    keys += ("input_tokens", "output_tokens", "latency_seconds")
    print("\n", json.dumps({k: result[k] for k in keys}, ensure_ascii=False))


if __name__ == "__main__":
    main()
