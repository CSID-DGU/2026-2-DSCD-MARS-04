"""완성 카드 비교 판정 provider.

- mode "replay": compare_fixtures.json에 저장된 판정을 돌려준다 (API 호출 없음, smoke용)
- mode "vision": 카드 PNG 묶음 + 원문 + 필수 정보를 비전 LLM에 보내 질문별 판정을 받는다
  (OPENAI_API_KEY 필요)

promptfoo Python provider 규약: call_api(prompt, options, context).
context["vars"]: case_id, service, case_dir(vision 모드)

출력 JSON: {"judgments": [{"question_id", "card_id", "fact_id", "verdict", "evidence", "reason",
                         "spans": [{"card_id", "card_text", "source_quote"}]}]}
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from experiments.promptfoo.compare.common import (
    ai_questions,
    card_ids_for,
    list_images,
    load_facts,
    load_questions,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "compare_fixtures.json"
DEFAULT_MODEL = "gpt-4.1-mini"

# 입력 단가(USD / 100만 토큰). 레포 ai/analysis/agent.py PRICES와 같은 값만 둔다.
PRICES = {"gpt-4.1-mini": (0.40, 1.60)}


def _replay(context: dict) -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    vars_ = context["vars"]
    output = data.get(vars_["case_id"], {}).get(vars_["service"])
    if output is None:
        return {"error": f"fixture에 {vars_['case_id']}/{vars_['service']} 판정이 없습니다."}
    return {
        "output": json.dumps(output, ensure_ascii=False),
        "tokenUsage": {"total": 0, "prompt": 0, "completion": 0},
        "cost": 0,
        "metadata": {"fixture": True},
    }


def build_instructions(spec: dict) -> str:
    lines = [
        "너는 카드뉴스 평가자다. 같은 원문으로 만든 카드뉴스 한 세트를 판정 질문에 따라 판정한다.",
        "어느 서비스가 만든 카드인지는 알려주지 않는다. 카드에 보이는 것만 근거로 판정한다.",
        "",
        "판정 규칙:",
        *[f"- {r}" for r in spec["rules"]],
        "",
        "출력 형식은 스키마로 고정된다. 카드 단위 질문은 card_id에 카드 번호, 필수 정보 질문은 "
        "fact_id에 필수 정보 ID를 넣고, 해당하지 않는 쪽은 null로 둔다. 판정을 빠뜨리지 않는다.",
        "spans는 C-01 NOT_MET, C-02 CONVEYED·DISTORTED에서만 채우고 나머지는 빈 목록으로 둔다.",
        "",
        "판정 질문:",
    ]
    for q in ai_questions(spec):
        unit = {"card": "카드마다", "set": "세트 전체에 한 번", "fact": "필수 정보마다"}[q["scope"]]
        values = ", ".join(spec["verdicts"][q["kind"]])
        na = f" 해당 없음 조건: {q['not_applicable']}." if q["not_applicable"] else ""
        lines.append(f"- {q['id']} {q['name']} ({unit}; {values}): {q['question']}{na}")
    return "\n".join(lines)


def output_schema(spec: dict) -> dict:
    """판정 출력 JSON 스키마 (strict). 모델이 형식을 어기지 못하게 한다."""
    span = {
        "type": "object",
        "additionalProperties": False,
        "required": ["card_id", "card_text", "source_quote"],
        "properties": {
            "card_id": {"type": "string"},
            "card_text": {"type": "string"},
            "source_quote": {"type": "string"},
        },
    }
    verdicts = sorted({v for vs in spec["verdicts"].values() for v in vs})
    judgment = {
        "type": "object",
        "additionalProperties": False,
        "required": ["question_id", "card_id", "fact_id", "verdict", "evidence", "reason", "spans"],
        "properties": {
            "question_id": {"type": "string", "enum": [q["id"] for q in ai_questions(spec)]},
            "card_id": {"type": ["string", "null"]},
            "fact_id": {"type": ["string", "null"]},
            "verdict": {"type": "string", "enum": verdicts},
            "evidence": {"type": "string"},
            "reason": {"type": "string"},
            "spans": {"type": "array", "items": span},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["judgments"],
        "properties": {"judgments": {"type": "array", "items": judgment}},
    }


def _image_part(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "input_image", "image_url": f"data:{mime};base64,{data}"}


def _vision(options: dict, context: dict) -> dict:
    from openai import OpenAI

    config = options.get("config", {})
    model = config.get("model") or os.getenv("COMPARE_JUDGE_MODEL") or DEFAULT_MODEL
    vars_ = context["vars"]
    case_dir = ROOT / vars_["case_dir"]
    images = list_images(case_dir / vars_["service"])
    if not images:
        return {"error": f"{case_dir / vars_['service']}에 카드 이미지가 없습니다."}
    source = (case_dir / "source.txt").read_text(encoding="utf-8")
    facts = load_facts(case_dir / "facts.json")
    spec = load_questions()

    content: list[dict] = [
        {"type": "input_text", "text": f"[원문]\n{source}"},
        {"type": "input_text", "text": "[필수 정보]\n" + json.dumps(facts, ensure_ascii=False)},
    ]
    for cid, path in zip(card_ids_for(images), images, strict=True):
        content.append({"type": "input_text", "text": f"[카드 {cid}]"})
        content.append(_image_part(path))

    started = time.perf_counter()
    response = OpenAI().responses.create(
        model=model,
        instructions=build_instructions(spec),
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "card_compare_judgments",
                "schema": output_schema(spec),
                "strict": True,
            }
        },
        temperature=0,
        store=False,
    )
    usage = response.usage
    tin, tout = (usage.input_tokens, usage.output_tokens) if usage else (0, 0)
    price = PRICES.get(model)
    return {
        "output": response.output_text,
        "tokenUsage": {"total": tin + tout, "prompt": tin, "completion": tout},
        "cost": (tin * price[0] + tout * price[1]) / 1_000_000 if price else None,
        "metadata": {"model": model, "seconds": round(time.perf_counter() - started, 2)},
    }


def call_api(prompt: str, options: dict, context: dict) -> dict:
    mode = options.get("config", {}).get("mode", "replay")
    if mode == "replay":
        return _replay(context)
    if mode == "vision":
        return _vision(options, context)
    return {"error": f"알 수 없는 mode: {mode}"}
