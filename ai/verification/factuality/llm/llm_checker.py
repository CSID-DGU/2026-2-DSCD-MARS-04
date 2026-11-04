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
from data_pipeline.schemas.card import Card, FinalCardOutput
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

CheckStatus = VerificationStatus | Literal["NOT_CHECKED"]


@lru_cache(maxsize=1)
def load_verification_prompt() -> str:
    path = Path(__file__).with_name("f_prompt.md")

    if not path.is_file():
        raise FileNotFoundError(f"사실성 검사 프롬프트를 찾을 수 없습니다: {path}")

    prompt = path.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError("사실성 검사 프롬프트가 비어 있습니다.")

    return prompt


class LLMJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: str
    status: VerificationStatus
    evidence: str
    reason: str
    error_type: str | None
    suggested_text: str | None


class LLMCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[LLMJudgment]


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
class LLMFactualityResult:
    document_id: str
    model: str
    status: CheckStatus
    cards: tuple[LLMCardResult, ...]
    input_tokens: int
    output_tokens: int


def aggregate_status(
    statuses: list[CheckStatus],
) -> CheckStatus:
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

    if evidence and evidence not in summary:
        return LLMJudgment(
            unit_id=judgment.unit_id,
            status="UNCERTAIN",
            evidence="",
            reason="모델이 제시한 근거가 그룹 요약문에 존재하지 않습니다.",
            error_type=None,
            suggested_text=None,
        )

    if judgment.status == "SUPPORTED" and not evidence:
        return LLMJudgment(
            unit_id=judgment.unit_id,
            status="UNCERTAIN",
            evidence="",
            reason="모델이 정상으로 판단했지만 근거 문구를 제시하지 않았습니다.",
            error_type=None,
            suggested_text=None,
        )

    if judgment.status == "NON_ASSERTIVE":
        return LLMJudgment(
            unit_id=judgment.unit_id,
            status="NON_ASSERTIVE",
            evidence=evidence,
            reason=reason,
            error_type=None,
            suggested_text=None,
        )

    return LLMJudgment(
        unit_id=judgment.unit_id,
        status=judgment.status,
        evidence=evidence,
        reason=reason,
        error_type=judgment.error_type,
        suggested_text=judgment.suggested_text,
    )


def validate_card_response(
    parsed: LLMCardResponse,
    units: list[CardTextUnit],
) -> dict[str, LLMJudgment]:
    expected_ids = [unit.unit_id for unit in units]
    returned_ids = [judgment.unit_id for judgment in parsed.results]

    if len(returned_ids) != len(expected_ids) or set(returned_ids) != set(expected_ids):
        raise ValueError("LLM이 반환한 필드 ID가 요청한 필드 ID와 일치하지 않습니다.")

    return {judgment.unit_id: judgment for judgment in parsed.results}


def verify_card(
    card: Card,
    units: list[CardTextUnit],
    summary: str,
    *,
    client: OpenAI,
    model: str,
) -> tuple[list[LLMFieldResult], int, int]:
    if not units:
        return [], 0, 0

    payload = {
        "card_id": card.card_id,
        "group_id": card.group_id,
        "card_title": card.title,
        "evidence_summary": summary,
        "fields": [
            {
                "unit_id": unit.unit_id,
                "field_path": unit.field_path,
                "card_text": unit.text,
                "card_context": unit.context,
            }
            for unit in units
        ],
    }

    response = client.responses.parse(
        model=model,
        instructions=load_verification_prompt(),
        input=json.dumps(payload, ensure_ascii=False),
        text_format=LLMCardResponse,
        store=False,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError(f"카드 {card.card_id}의 사실성 검사 결과를 파싱하지 못했습니다.")

    judgment_map = validate_card_response(parsed, units)

    results = []

    for unit in units:
        judgment = validate_judgment(
            judgment_map[unit.unit_id],
            summary,
        )

        results.append(
            LLMFieldResult(
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
        )

    usage = response.usage

    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0

    return results, input_tokens, output_tokens


def check_llm_factuality(
    groups: list[Group],
    final_cards: FinalCardOutput,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
) -> LLMFactualityResult:
    selected_model = model or os.getenv("VERIFICATION_MODEL") or DEFAULT_MODEL

    group_map = {group.group_id: group.summary for group in groups}

    if len(group_map) != len(groups):
        raise ValueError("그룹 ID가 중복되었습니다.")

    card_ids = [card.card_id for card in final_cards.cards]

    if len(card_ids) != len(set(card_ids)):
        raise ValueError("카드 ID가 중복되었습니다.")

    for card in final_cards.cards:
        if card.group_id is not None and card.group_id not in group_map:
            raise ValueError(f"카드 {card.card_id}의 그룹 {card.group_id}을 찾을 수 없습니다.")

    units = extract_card_texts(final_cards)
    units_by_card: dict[str, list[CardTextUnit]] = {}

    for unit in units:
        units_by_card.setdefault(
            unit.card_id,
            [],
        ).append(unit)

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

        card_units = units_by_card.get(card.card_id, [])

        if not card_units:
            card_results.append(
                LLMCardResult(
                    card_id=card.card_id,
                    group_id=card.group_id,
                    status="NOT_CHECKED",
                    fields=(),
                )
            )
            continue

        field_results, input_tokens, output_tokens = verify_card(
            card=card,
            units=card_units,
            summary=group_map[card.group_id],
            client=client,
            model=selected_model,
        )

        card_results.append(
            LLMCardResult(
                card_id=card.card_id,
                group_id=card.group_id,
                status=aggregate_status([field.status for field in field_results]),
                fields=tuple(field_results),
            )
        )

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

    return LLMFactualityResult(
        document_id=final_cards.document_id,
        model=selected_model,
        status=aggregate_status([card.status for card in card_results]),
        cards=tuple(card_results),
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
