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


# 한 요청에 카드 8~12장 × 질문 16개 + 필수 정보 판정을 몰아넣으면 gpt-4.1-mini가 판정을 빠뜨리고
# 판정값·ID를 섞는다(11-08 실측: 38건 중 7건만 형식 통과). 그래서 질문을 세 번에 나눠 묻는다.
PASSES = (("visual", None), ("factuality", {"C-01"}), ("completeness", {"C-02"}))


def pass_questions(spec: dict, ids: set[str] | None) -> list[dict]:
    """ids가 None이면 C-01·C-02를 뺀 시각·구성 질문, 아니면 그 질문만."""
    text_ids = {i for _, ids_ in PASSES if ids_ for i in ids_}
    return [q for q in ai_questions(spec) if (q["id"] in ids if ids else q["id"] not in text_ids)]


def build_instructions(spec: dict, questions: list[dict] | None = None) -> str:
    questions = questions if questions is not None else ai_questions(spec)
    lines = [
        "너는 카드뉴스 평가자다. 같은 원문으로 만든 카드뉴스 한 세트를 판정 질문에 따라 판정한다.",
        "어느 서비스가 만든 카드인지는 알려주지 않는다. 카드에 보이는 것만 근거로 판정한다.",
        "",
        "판정 규칙:",
        *[f"- {r}" for r in spec["rules"]],
        "",
        "출력 형식은 스키마로 고정된다. 판정할 칸마다 '질문 ID|카드 번호'(카드 단위), "
        "'질문 ID|필수 정보 ID'(필수 정보 단위), '질문 ID|SET'(세트 단위) 이름의 속성이 있고 "
        "모두 채운다.",
        "spans는 C-01 NOT_MET, C-02 CONVEYED·PARTIALLY_CONVEYED·DISTORTED에서만 채우고 "
        "나머지는 빈 목록으로 둔다.",
        "",
        "판정 질문:",
    ]
    for q in questions:
        unit = {"card": "카드마다", "set": "세트 전체에 한 번", "fact": "필수 정보마다"}[q["scope"]]
        values = ", ".join(spec["verdicts"][q["kind"]])
        na = f" 해당 없음 조건: {q['not_applicable']}." if q["not_applicable"] else ""
        lines.append(f"- {q['id']} {q['name']} ({unit}; {values}): {q['question']}{na}")
    return "\n".join(lines)


def slots(questions: list[dict], card_ids: list[str], fact_ids: list[str]) -> list[tuple]:
    """판정해야 할 칸 (이름, 질문, card_id, fact_id).

    이름은 '질문 ID|카드 번호·필수 정보 ID·SET'.
    """
    out = []
    for q in questions:
        refs = {
            "card": [(c, None) for c in card_ids],
            "set": [(None, None)],
            "fact": [(None, f) for f in fact_ids],
        }
        for cid, fid in refs[q["scope"]]:
            out.append((f"{q['id']}|{cid or fid or 'SET'}", q, cid, fid))
    return out


def output_schema(
    spec: dict,
    questions: list[dict] | None = None,
    card_ids: list[str] | None = None,
    fact_ids: list[str] | None = None,
) -> dict:
    """판정 출력 JSON 스키마 (strict).

    판정할 칸마다 필수 속성을 하나씩 둬서 빠뜨리거나 ID·판정값을 섞지 못하게 한다.
    """
    questions = questions if questions is not None else ai_questions(spec)
    span = {
        "type": "object",
        "additionalProperties": False,
        "required": ["card_id", "card_text", "source_line"],
        "properties": {
            "card_id": {"type": "string"},
            "card_text": {"type": "string"},
            "source_line": {"type": "integer"},
        },
    }

    def judgment(q: dict) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["verdict", "evidence", "reason", "spans"],
            "properties": {
                "verdict": {"type": "string", "enum": spec["verdicts"][q["kind"]]},
                "evidence": {"type": "string"},
                "reason": {"type": "string"},
                "spans": {"type": "array", "items": span},
            },
        }

    table = slots(questions, card_ids or [], fact_ids or [])
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [name for name, *_ in table],
        "properties": {name: judgment(q) for name, q, *_ in table},
    }


def _quote(span: dict, lines: list[str]) -> dict:
    """모델은 원문 줄 번호만 고른다. 원문을 옮겨 쓰다 바꾸는 일을 막으려고 인용은 코드가 채운다."""
    span = dict(span)
    n = span.pop("source_line", None)
    ok = isinstance(n, int) and 1 <= n <= len(lines)
    span["source_quote"] = lines[n - 1] if ok else f"(없는 원문 줄 {n})"
    return span


def to_judgments(answer: dict, table: list[tuple], lines: list[str] | None = None) -> list[dict]:
    """칸 이름으로 받은 판정을 assertion·내보내기가 쓰는 목록 형식으로 바꾼다."""
    out = []
    for name, q, cid, fid in table:
        if name not in answer:
            continue
        item = {"question_id": q["id"], "card_id": cid, "fact_id": fid, **answer[name]}
        if lines is not None:
            item["spans"] = [_quote(sp, lines) for sp in item.get("spans", [])]
        out.append(item)
    return out


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
    lines = (case_dir / "source.txt").read_text(encoding="utf-8").splitlines()
    facts = load_facts(case_dir / "facts.json")
    spec = load_questions()

    card_ids = card_ids_for(images)
    content: list[dict] = [
        {
            "type": "input_text",
            "text": "[원문, 줄 번호: 내용]\n"
            + "\n".join(f"{i}: {t}" for i, t in enumerate(lines, 1)),
        },
        {"type": "input_text", "text": "[필수 정보]\n" + json.dumps(facts, ensure_ascii=False)},
    ]
    for cid, path in zip(card_ids, images, strict=True):
        content.append({"type": "input_text", "text": f"[카드 {cid}]"})
        content.append(_image_part(path))

    fact_ids = [f["id"] for f in facts]
    started = time.perf_counter()
    judgments: list[dict] = []
    tin = tout = 0
    client = OpenAI()
    for name, ids in PASSES:
        questions = pass_questions(spec, ids)
        response = client.responses.create(
            model=model,
            instructions=build_instructions(spec, questions),
            input=[{"role": "user", "content": content}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": f"card_compare_{name}",
                    "schema": output_schema(spec, questions, card_ids, fact_ids),
                    "strict": True,
                }
            },
            temperature=0,
            store=False,
        )
        judgments += to_judgments(
            json.loads(response.output_text), slots(questions, card_ids, fact_ids), lines
        )
        if response.usage:
            tin += response.usage.input_tokens
            tout += response.usage.output_tokens
    price = PRICES.get(model)
    return {
        "output": json.dumps({"judgments": judgments}, ensure_ascii=False),
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
