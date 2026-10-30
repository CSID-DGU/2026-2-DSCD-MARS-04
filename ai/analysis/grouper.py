import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.sentence_splitter import split_sentences

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).with_name("prompts") / "grouping.md"
GROUPING_MODEL = "gpt-4.1-mini"
TEMPERATURE = 0
MAX_GROUPS = 10


class SentenceGroup(BaseModel):
    group_id: str
    sentence_ids: list[str]


class GroupingResult(BaseModel):
    groups: list[SentenceGroup]


def check_grouping(sentence_ids: list[str], groups: list[dict]) -> list[str]:
    position = {sentence_id: index for index, sentence_id in enumerate(sentence_ids)}
    errors = []
    used = []

    for group in groups:
        group_id = group["group_id"]
        ids = group["sentence_ids"]
        if not ids:
            errors.append(f"{group_id}: 문장이 없는 빈 그룹입니다.")
            continue

        unknown = [i for i in ids if i not in position]
        if unknown:
            errors.append(f"{group_id}: 없는 문장 ID가 있습니다 ({', '.join(unknown)}).")

        places = sorted(position[i] for i in ids if i in position)
        if places and places != list(range(places[0], places[0] + len(places))):
            errors.append(f"{group_id}: 붙어 있지 않은 문장을 묶었습니다 ({', '.join(ids)}).")

        used += ids

    duplicated = [i for i in sentence_ids if used.count(i) > 1]
    if duplicated:
        errors.append(f"두 번 이상 들어간 문장이 있습니다 ({', '.join(duplicated)}).")

    missing = [i for i in sentence_ids if i not in used]
    if missing:
        errors.append(f"어느 그룹에도 들어가지 않은 문장이 있습니다 ({', '.join(missing)}).")

    return errors


def order_groups(groups: list[dict], sentence_ids: list[str]) -> list[dict]:
    """그룹 안 문장과 그룹 순서를 원문 순서로 맞추고 G1, G2, ... 로 다시 번호를 붙인다."""
    position = {sentence_id: index for index, sentence_id in enumerate(sentence_ids)}
    ordered = sorted(
        (sorted(group["sentence_ids"], key=position.__getitem__) for group in groups),
        key=lambda ids: position[ids[0]],
    )
    return [{"group_id": f"G{n}", "sentence_ids": ids} for n, ids in enumerate(ordered, start=1)]


def call_grouping(
    sentences: list[dict],
    max_groups: int,
    *,
    previous_errors: list[str] | None = None,
    model: str | None = None,
    client: OpenAI | None = None,
) -> dict:
    load_dotenv(ROOT / ".env")
    model = model or os.getenv("GROUPING_MODEL", GROUPING_MODEL)
    client = client or OpenAI()

    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    payload = {"max_groups": max_groups, "sentences": sentences}
    if previous_errors:
        payload["previous_errors"] = previous_errors
    user_input = json.dumps(payload, ensure_ascii=False)

    started = time.perf_counter()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        text_format=GroupingResult,
        temperature=TEMPERATURE,
    )
    latency = time.perf_counter() - started

    if response.output_parsed is None:
        raise RuntimeError("스키마에 맞는 그룹화 결과가 없습니다.")

    return {
        "groups": [group.model_dump() for group in response.output_parsed.groups],
        "model": model,
        "response_model": getattr(response, "model", None),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_seconds": round(latency, 2),
    }


def group_sentences(
    sentences: list[dict],
    max_groups: int = MAX_GROUPS,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
    max_retries: int = 1,
) -> dict:
    """그룹화하고 검사한다. 문제가 있으면 오류를 알려주며 max_retries번까지 다시 요청한다."""
    sentence_ids = [sentence["sentence_id"] for sentence in sentences]
    calls = []
    errors: list[str] = []

    for attempt in range(1, max_retries + 2):
        result = call_grouping(
            sentences, max_groups, previous_errors=errors, model=model, client=client
        )
        errors = check_grouping(sentence_ids, result["groups"])
        calls.append({"attempt": attempt, **result, "errors": errors})
        if not errors:
            break

    groups = calls[-1]["groups"]
    if not errors:
        groups = order_groups(groups, sentence_ids)

    return {
        "groups": groups,
        "valid": not errors,
        "errors": errors,
        "first_try_valid": len(calls) == 1 and not errors,
        "attempts": len(calls),
        "over_max_groups": len(groups) > max_groups,
        "model": calls[-1]["model"],
        "response_model": calls[-1]["response_model"],
        "max_groups": max_groups,
        "max_retries": max_retries,
        "temperature": TEMPERATURE,
        "input_tokens": sum(call["input_tokens"] for call in calls),
        "output_tokens": sum(call["output_tokens"] for call in calls),
        "latency_seconds": round(sum(call["latency_seconds"] for call in calls), 2),
        "calls": calls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="기사 하나를 그룹화해 본다")
    parser.add_argument("--file", default="data/samples/original_text.xlsx")
    parser.add_argument("--index", type=int, default=0, help="몇 번째 기사 (0부터)")
    parser.add_argument("--model", help="GROUPING_MODEL 대신 쓸 모델")
    args = parser.parse_args()

    article = load_articles(args.file, limit=args.index + 1)[args.index]
    sentences = split_sentences(article["source_text"])
    max_groups = MAX_GROUPS

    print(f"기사: {article['document_id']}")
    for sentence in sentences:
        print(f"[{sentence['sentence_id']}] {sentence['text']}")
    print(f"\n문장 {len(sentences)}개, 그룹 상한 {max_groups}개\n")

    result = group_sentences(sentences, max_groups, model=args.model)
    result.pop("calls")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
