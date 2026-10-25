import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai.analysis import grouper, summarizer
from ai.analysis.grouper import ROOT, group_sentences
from ai.analysis.summarizer import summarize_groups
from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.sentence_splitter import split_sentences
from data_pipeline.schemas.group import GroupAnalysis

DEFAULT_LOG_PATH = ROOT / "logs" / "analysis.jsonl"

# 1M 토큰당 달러 (입력, 출력). 추정 비용용이며 실제 청구액은 OpenAI 사용량 페이지에서 확인한다.
# 가격이 바뀌면 여기만 고치면 된다. 표에 없는 모델은 비용을 null로 남긴다.
PRICES_PER_1M = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    """가장 길게 일치하는 이름으로 가격을 찾는다 (gpt-4.1-mini-2025-04-14 → gpt-4.1-mini)."""
    if not model:
        return None
    matches = [name for name in PRICES_PER_1M if model == name or model.startswith(name + "-")]
    if not matches:
        return None
    input_price, output_price = PRICES_PER_1M[max(matches, key=len)]
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)


def call_record(call: dict, output_key: str) -> dict:
    """호출 한 번의 기록. 모델이 낸 응답(문장 ID, 요약)과 그 응답이 걸린 검사 결과."""
    record = {
        "attempt": call["attempt"],
        "response_model": call["response_model"],
        "input_tokens": call["input_tokens"],
        "output_tokens": call["output_tokens"],
        "latency_seconds": call["latency_seconds"],
        "estimated_cost_usd": estimate_cost(
            call["response_model"] or call["model"], call["input_tokens"], call["output_tokens"]
        ),
        "response": call[output_key],
        "errors": call["errors"],
    }
    if "group_ids" in call:
        record["requested_group_ids"] = call["group_ids"]
    return record


def stage_record(
    result: dict, prompt_path: Path, extra_keys: tuple[str, ...], output_key: str
) -> dict:
    keys = ("model", "response_model", "attempts", "input_tokens", "output_tokens")
    keys += ("latency_seconds",)
    calls = [call_record(call, output_key) for call in result["calls"]]
    costs = [call["estimated_cost_usd"] for call in calls]
    return {
        **{key: result[key] for key in keys + extra_keys},
        "estimated_cost_usd": None if None in costs else round(sum(costs), 6),
        "prompt_sha256": sha256(prompt_path.read_text(encoding="utf-8").strip()),
        "calls": calls,
    }


def _analyze(document_id: str, text: str, record: dict, client=None) -> dict:
    record["stage"] = "split"
    sentences = split_sentences(text)
    record["sentence_count"] = len(sentences)
    if not sentences:
        raise ValueError("문장이 없습니다.")

    record["stage"] = "grouping"
    grouping = group_sentences(sentences, client=client)
    record["grouping"] = stage_record(
        grouping,
        grouper.PROMPT_PATH,
        ("max_groups", "max_retries", "temperature", "valid", "first_try_valid")
        + ("over_max_groups", "errors"),
        output_key="groups",
    )
    if not grouping["valid"]:
        raise RuntimeError("그룹화 검사를 통과하지 못했습니다.")

    record["stage"] = "summary"
    summary = summarize_groups(sentences, grouping["groups"], client=client)
    record["summary"] = stage_record(
        summary,
        summarizer.PROMPT_PATH,
        ("max_retries", "temperature", "retried_group_ids", "fallback_group_ids")
        + ("fallback_reasons",),
        output_key="summaries",
    )

    record["stage"] = "output"
    groups = [GroupAnalysis.model_validate(group) for group in summary["groups"]]
    return {"document_id": document_id, "groups": [group.model_dump() for group in groups]}


def analyze(document_id: str, text: str, *, log_path: Path | None = None, client=None) -> dict:
    """원문 하나를 분석해 {"document_id", "groups": [GroupAnalysis, ...]}를 돌려준다."""
    started = time.perf_counter()
    record = {
        "run_id": str(uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
        "source_sha256": sha256(text),
        "status": "failed",
    }
    try:
        result = _analyze(document_id, text, record, client)
        record.update(status="success", result=result)
        return result
    except Exception as exc:
        # 오류 메시지에는 원문이나 키가 섞일 수 있어 종류와 단계만 남긴다.
        record["error"] = {"type": type(exc).__name__, "stage": record.get("stage")}
        raise
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        costs = [record[s]["estimated_cost_usd"] for s in ("grouping", "summary") if s in record]
        record["estimated_cost_usd"] = None if None in costs else round(sum(costs), 6)
        destination = Path(log_path or os.getenv("ANALYSIS_LOG_PATH", DEFAULT_LOG_PATH))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            print("경고: 분석 로그 파일을 기록하지 못했습니다.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="기사 하나를 분석해 GroupAnalysis JSON을 만든다")
    parser.add_argument("--file", default="data/samples/original_text.xlsx")
    parser.add_argument("--index", type=int, default=0, help="몇 번째 기사 (0부터)")
    args = parser.parse_args()

    article = load_articles(args.file, limit=args.index + 1)[args.index]
    result = analyze(article["document_id"], article["source_text"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
