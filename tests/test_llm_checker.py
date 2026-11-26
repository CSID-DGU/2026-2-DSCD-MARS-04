import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from ai.verification.shared.card_text_extractor import (
    CardTextUnit,
    extract_card_texts,
)
from data_pipeline.schemas.card import FinalCardOutput
from data_pipeline.schemas.group import Group

load_dotenv()

DEFAULT_MODEL = "gpt-4.1-mini"

VerificationStatus = Literal[
    "SUPPORTED",
    "POSSIBLE_DISTORTION",
    "INSUFFICIENT_EVIDENCE",
    "UNCERTAIN",
    "NON_ASSERTIVE",
]

CheckStatus = Literal[
    "SUPPORTED",
    "POSSIBLE_DISTORTION",
    "INSUFFICIENT_EVIDENCE",
    "UNCERTAIN",
    "NON_ASSERTIVE",
    "NOT_CHECKED",
]


@lru_cache(maxsize=1)
def load_verification_prompt() -> str:
    prompt_path = Path(__file__).with_name("verification_prompt.md")

    if not prompt_path.is_file():
        raise FileNotFoundError(f"검증 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")

    prompt = prompt_path.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError("검증 프롬프트 파일이 비어 있습니다.")

    return prompt


class LLMJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    evidence: str
    reason: str
    error_type: str | None
    suggested_text: str | None


@dataclass(frozen=True)
class LLMFieldResult:
    unit_id: str
    card_id: str
    group_id: str
    field_path: str
    card_text: str
    status: VerificationStatus
    evidence: str
    reason: str
    error_type: str | None
    suggested_text: str | None


@dataclass(frozen=True)
class LLMCardResult:
    card_id: str
    group_id: str | None
    status: CheckStatus
    fields: tuple[LLMFieldResult, ...]


@dataclass(frozen=True)
class LLMCompletenessResult:
    document_id: str
    model: str
    status: CheckStatus
    cards: tuple[LLMCardResult, ...]
    input_tokens: int
    output_tokens: int


def aggregate_status(statuses: list[CheckStatus]) -> CheckStatus:
    if not statuses:
        return "NOT_CHECKED"

    if "POSSIBLE_DISTORTION" in statuses:
        return "POSSIBLE_DISTORTION"

    if "UNCERTAIN" in statuses:
        return "UNCERTAIN"

    if "INSUFFICIENT_EVIDENCE" in statuses:
        return "INSUFFICIENT_EVIDENCE"

    if "NOT_CHECKED" in statuses:
        return "NOT_CHECKED"

    if "SUPPORTED" in statuses:
        return "SUPPORTED"

    return "NON_ASSERTIVE"


def validate_judgment(
    judgment: LLMJudgment,
    summary: str,
) -> LLMJudgment:
    evidence = judgment.evidence.strip()
    reason = judgment.reason.strip()
    status = judgment.status
    error_type = judgment.error_type
    suggested_text = judgment.suggested_text

    if evidence and evidence not in summary:
        return LLMJudgment(
            status="UNCERTAIN",
            evidence="",
            reason="모델이 제시한 근거 문구가 그룹 요약문에 존재하지 않습니다.",
            error_type=None,
            suggested_text=None,
        )

    if status == "SUPPORTED" and not evidence:
        return LLMJudgment(
            status="UNCERTAIN",
            evidence="",
            reason="모델이 정상으로 판단했지만 근거 문구를 제시하지 않았습니다.",
            error_type=None,
            suggested_text=None,
        )

    if status == "NON_ASSERTIVE":
        return LLMJudgment(
            status="NON_ASSERTIVE",
            evidence=evidence,
            reason=reason,
            error_type=None,
            suggested_text=None,
        )

    return LLMJudgment(
        status=status,
        evidence=evidence,
        reason=reason,
        error_type=error_type,
        suggested_text=suggested_text,
    )


def verify_field(
    unit: CardTextUnit,
    summary: str,
    *,
    client: OpenAI,
    model: str,
    card_title: str,
) -> tuple[LLMFieldResult, int, int]:
    payload = {
        "group_id": unit.group_id,
        "field_path": unit.field_path,
        "card_title": card_title,
        "card_text": unit.text,
        "card_context": unit.context,
        "evidence_summary": summary,
    }

    response = client.responses.parse(
        model=model,
        instructions=load_verification_prompt(),
        input=json.dumps(payload, ensure_ascii=False),
        text_format=LLMJudgment,
        store=False,
    )

    judgment = response.output_parsed

    if judgment is None:
        raise ValueError(f"LLM 응답을 파싱하지 못했습니다: {unit.unit_id}")

    judgment = validate_judgment(
        judgment=judgment,
        summary=summary,
    )

    field_result = LLMFieldResult(
        unit_id=unit.unit_id,
        card_id=unit.card_id,
        group_id=unit.group_id,
        field_path=unit.field_path,
        card_text=unit.text,
        status=judgment.status,
        evidence=judgment.evidence,
        reason=judgment.reason,
        error_type=judgment.error_type,
        suggested_text=judgment.suggested_text,
    )

    usage = response.usage

    input_tokens = usage.input_tokens if usage is not None else 0
    output_tokens = usage.output_tokens if usage is not None else 0

    return field_result, input_tokens, output_tokens


def check_llm_completeness(
    groups: list[Group],
    final_cards: FinalCardOutput,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
) -> LLMCompletenessResult:
    selected_model = model or os.getenv("VERIFICATION_MODEL") or DEFAULT_MODEL

    group_map = {group.group_id: group.summary for group in groups}

    for card in final_cards.cards:
        if card.group_id is not None and card.group_id not in group_map:
            raise ValueError(f"카드 {card.card_id}의 그룹 {card.group_id}을 찾을 수 없습니다.")

    units = extract_card_texts(final_cards)

    units_by_card: dict[str, list[CardTextUnit]] = {}

    for unit in units:
        units_by_card.setdefault(unit.card_id, []).append(unit)

    if units and client is None:
        client = OpenAI()

    card_results: list[LLMCardResult] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for card in final_cards.cards:
        if card.group_id is None:
            card_results.append(
                LLMCardResult(
                    card_id=card.card_id,
                    group_id=None,
                    status="NOT_CHECKED",
                    fields=(),
                )
            )
            continue

        summary = group_map[card.group_id]
        field_results: list[LLMFieldResult] = []

        for unit in units_by_card.get(card.card_id, []):
            result, input_tokens, output_tokens = verify_field(
                unit=unit,
                summary=summary,
                client=client,
                model=selected_model,
                card_title=card.title or "",
            )

            field_results.append(result)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

        card_results.append(
            LLMCardResult(
                card_id=card.card_id,
                group_id=card.group_id,
                status=aggregate_status([field.status for field in field_results]),
                fields=tuple(field_results),
            )
        )

    overall_status = aggregate_status([card.status for card in card_results])

    return LLMCompletenessResult(
        document_id=final_cards.document_id,
        model=selected_model,
        status=overall_status,
        cards=tuple(card_results),
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
