"""사실성 판정: 검사할 글이 근거 원문으로 뒷받침되는지 본다.

순서: 숫자 규칙(원문에 없는 숫자면 바로 FAIL) → 남은 항목만 LLM 판정.
요약 단계(그룹 원문 vs 그룹 요약)와 카드 단계(sids 문장 vs 카드 문구)에서 같이 쓴다.
by_sentence=True면 검사할 글을 문장으로 나눠 문장마다 판정하고, 한 문장이라도 FAIL이면 FAIL이다.
(평가 데이터 mFACE가 한 문장 요약이라, 여러 문장 글도 같은 조건에서 판정하기 위함)
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from ai.verification.consistency.numbers import find_new_numbers, number_context
from data_pipeline.extraction.llm.sentence_splitter import split_sentences

ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = Path(__file__).with_name("prompts") / "consistency.md"
CONSISTENCY_MODEL = "gpt-6-luna"
TEMPERATURE = 0
REQUEST_TIMEOUT = 60  # 초. 응답이 없으면 기본값(10분)까지 기다리지 않고 다시 시도한다


class Problem(BaseModel):
    quote: str
    reason: str


class Judgment(BaseModel):
    item_id: str
    supported: bool
    problems: list[Problem]


class JudgmentResult(BaseModel):
    judgments: list[Judgment]


def check_numbers(item: dict) -> dict | None:
    """원문에 없는 숫자가 있으면 FAIL 결과를, 없으면 None을 돌려준다."""
    new = find_new_numbers(item["source"], item["text"])
    if not new:
        return None
    return {
        "item_id": item["item_id"],
        "status": "FAIL",
        "by": "rule",
        "problems": [
            {"quote": number_context(n, item["text"]), "reason": f"원문에 없는 숫자입니다: {n}"}
            for n in new
        ],
    }


def call_judge(
    items: list[dict], *, model: str | None = None, client: OpenAI | None = None
) -> dict:
    load_dotenv(ROOT / ".env")
    model = model or os.getenv("CONSISTENCY_MODEL", CONSISTENCY_MODEL)
    client = client or OpenAI(timeout=REQUEST_TIMEOUT, max_retries=2)

    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    keys = ("item_id", "source", "text", "previous_text")
    payload = {"items": [{k: i[k] for k in keys if k in i} for i in items]}
    # gpt-5·6 계열은 생각을 꺼야 temperature를 쓸 수 있다
    extra = {"reasoning": {"effort": "none"}} if model.startswith(("gpt-5", "gpt-6")) else {}

    started = time.perf_counter()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text_format=JudgmentResult,
        temperature=TEMPERATURE,
        **extra,
    )
    latency = time.perf_counter() - started

    if response.output_parsed is None:
        raise RuntimeError("스키마에 맞는 판정 결과가 없습니다.")

    return {
        "judgments": [j.model_dump() for j in response.output_parsed.judgments],
        "model": model,
        "response_model": getattr(response, "model", None),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_seconds": round(latency, 2),
    }


def _check(items: list[dict], *, model: str | None = None, client: OpenAI | None = None) -> dict:
    """items를 그대로 판정한다 (숫자 규칙 → LLM)."""
    results = {}
    for item in items:
        rule_result = check_numbers(item)
        if rule_result:
            results[item["item_id"]] = rule_result

    rest = [item for item in items if item["item_id"] not in results]
    call = None
    if rest:
        call = call_judge(rest, model=model, client=client)
        rest_ids = {item["item_id"] for item in rest}
        for j in call["judgments"]:
            if j["item_id"] in rest_ids:
                results[j["item_id"]] = {
                    "item_id": j["item_id"],
                    "status": "PASS" if j["supported"] else "FAIL",
                    "by": "llm",
                    "problems": [] if j["supported"] else j["problems"],
                }

    missing = [item["item_id"] for item in items if item["item_id"] not in results]
    if missing:
        raise RuntimeError(f"판정이 빠진 항목이 있습니다: {', '.join(missing)}")

    return {"results": [results[item["item_id"]] for item in items], "call": call}


def split_into_sentences(items: list[dict]) -> list[dict]:
    """항목마다 text를 문장으로 나눈다. 앞 문장은 참고용 previous_text로 붙인다."""
    units = []
    for item in items:
        sentences = [s["text"] for s in split_sentences(item["text"])] or [item["text"]]
        for n, sentence in enumerate(sentences, 1):
            unit = {"item_id": f"{item['item_id']}#{n}", "source": item["source"], "text": sentence}
            if n > 1:
                unit["previous_text"] = sentences[n - 2]
            units.append(unit)
    return units


def check_consistency(
    items: list[dict],
    *,
    by_sentence: bool = False,
    model: str | None = None,
    client: OpenAI | None = None,
) -> dict:
    """items: [{"item_id", "source", "text"}] → 항목마다 PASS/FAIL과 이유."""
    if not by_sentence:
        return _check(items, model=model, client=client)

    checked = _check(split_into_sentences(items), model=model, client=client)
    by_item = {}
    for unit in checked["results"]:
        by_item.setdefault(unit["item_id"].rsplit("#", 1)[0], []).append(unit)
    results = []
    for item in items:
        units = by_item[item["item_id"]]
        failed = [u for u in units if u["status"] == "FAIL"]
        results.append(
            {
                "item_id": item["item_id"],
                "status": "FAIL" if failed else "PASS",
                "by": "rule" if failed and all(u["by"] == "rule" for u in failed) else "llm",
                "problems": [p for u in failed for p in u["problems"]],
                "sentences": [
                    {"text_index": i, "status": u["status"]} for i, u in enumerate(units, 1)
                ],
            }
        )
    return {"results": results, "call": checked["call"]}
