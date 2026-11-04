import json
import os
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from ai.verification.completeness.llm.llm_checker import CompletenessResult
from ai.verification.factuality.llm.llm_checker import LLMFactualityResult

load_dotenv()

DEFAULT_MODEL = "gpt-4.1-mini"

FeedbackCategory = Literal["ERROR", "OMISSION", "REVIEW"]

FeedbackStatus = Literal[
    "ISSUES_FOUND",
    "REVIEW_NEEDED",
    "PASSED",
    "NOT_CHECKED",
]

FACTUALITY_ISSUES = {
    "POSSIBLE_DISTORTION",
    "INSUFFICIENT_EVIDENCE",
    "UNCERTAIN",
}

COMPLETENESS_ISSUES = {
    "DISTORTED",
    "PARTIALLY_COVERED",
    "MISSING",
    "UNCERTAIN",
}


class FeedbackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    category: FeedbackCategory
    description: str
    suggested_text: str | None
    source_ids: list[str]
    card_ids: list[str]


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FeedbackItem]


@dataclass(frozen=True)
class MergedFeedbackResult:
    document_id: str
    model: str
    status: FeedbackStatus
    items: tuple[FeedbackItem, ...]
    unchecked: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    factuality: LLMFactualityResult
    completeness: CompletenessResult


@lru_cache(maxsize=1)
def load_feedback_prompt() -> str:
    path = Path(__file__).with_name("feedback_prompt.md")

    if not path.is_file():
        raise FileNotFoundError(f"피드백 프롬프트 파일을 찾을 수 없습니다: {path}")

    prompt = path.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError("피드백 프롬프트가 비어 있습니다.")

    return prompt


def collect_findings(
    factuality: LLMFactualityResult,
    completeness: CompletenessResult,
) -> tuple[list[dict], list[str], set[str]]:
    findings = []
    unchecked = []
    valid_card_ids = {card.card_id for card in factuality.cards}

    for card in factuality.cards:
        if card.status == "NOT_CHECKED":
            unchecked.append(f"factuality:{card.card_id}")

        for field in card.fields:
            if field.status not in FACTUALITY_ISSUES:
                continue

            findings.append(
                {
                    "source_id": f"F:{field.unit_id}",
                    "kind": "FAITHFULNESS",
                    "status": field.status,
                    "card_id": field.card_id,
                    "related_card_ids": [field.card_id],
                    "text": field.card_text,
                    "evidence": field.evidence,
                    "reason": field.reason,
                    "suggested_text": field.suggested_text,
                    "missing_elements": [],
                }
            )

    if completeness.status == "NOT_CHECKED":
        unchecked.append("completeness")

    for fact in completeness.results:
        if fact.status not in COMPLETENESS_ISSUES:
            continue

        findings.append(
            {
                "source_id": f"C:{fact.fact_id}",
                "kind": "COMPLETENESS",
                "status": fact.status,
                "card_id": None,
                "related_card_ids": fact.matched_card_ids,
                "text": "",
                "evidence": "",
                "reason": fact.reason,
                "suggested_text": None,
                "missing_elements": fact.missing_elements,
            }
        )

    source_ids = [finding["source_id"] for finding in findings]

    if len(source_ids) != len(set(source_ids)):
        raise ValueError("통합할 검사 결과 ID가 중복되었습니다.")

    return findings, unchecked, valid_card_ids


def validate_feedback(
    response: FeedbackResponse,
    findings: list[dict],
    valid_card_ids: set[str],
) -> tuple[FeedbackItem, ...]:
    expected_ids = {finding["source_id"] for finding in findings}

    returned_ids = [source_id for item in response.items for source_id in item.source_ids]

    if Counter(returned_ids) != Counter(expected_ids):
        raise ValueError("통합 피드백에 원본 검사 결과가 누락되거나 중복되었습니다.")

    for item in response.items:
        if not item.source_ids:
            raise ValueError("근거 검사 ID가 없는 피드백이 있습니다.")

        if not set(item.card_ids).issubset(valid_card_ids):
            raise ValueError("피드백에 존재하지 않는 카드 ID가 포함되어 있습니다.")

        if not item.title.strip() or not item.description.strip():
            raise ValueError("제목이나 설명이 비어 있는 피드백이 있습니다.")

    return tuple(response.items)


def determine_status(
    findings: list[dict],
    unchecked: list[str],
) -> FeedbackStatus:
    actionable_statuses = {
        "POSSIBLE_DISTORTION",
        "DISTORTED",
        "PARTIALLY_COVERED",
        "MISSING",
    }

    if any(finding["status"] in actionable_statuses for finding in findings):
        return "ISSUES_FOUND"

    if findings:
        return "REVIEW_NEEDED"

    if unchecked:
        return "NOT_CHECKED"

    return "PASSED"


def merge_feedback(
    factuality: LLMFactualityResult,
    completeness: CompletenessResult,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
) -> MergedFeedbackResult:
    if factuality.document_id != completeness.document_id:
        raise ValueError("사실성 검사와 완전성 검사의 document_id가 다릅니다.")

    selected_model = (
        model or os.getenv("FEEDBACK_MODEL") or os.getenv("VERIFICATION_MODEL") or DEFAULT_MODEL
    )

    findings, unchecked, valid_card_ids = collect_findings(
        factuality,
        completeness,
    )

    status = determine_status(findings, unchecked)

    if not findings:
        return MergedFeedbackResult(
            document_id=factuality.document_id,
            model=selected_model,
            status=status,
            items=(),
            unchecked=tuple(unchecked),
            input_tokens=0,
            output_tokens=0,
            factuality=factuality,
            completeness=completeness,
        )

    if client is None:
        client = OpenAI()

    payload = {
        "document_id": factuality.document_id,
        "findings": findings,
    }

    response = client.responses.parse(
        model=selected_model,
        instructions=load_feedback_prompt(),
        input=json.dumps(payload, ensure_ascii=False),
        text_format=FeedbackResponse,
        store=False,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError("통합 피드백 응답을 파싱하지 못했습니다.")

    items = validate_feedback(
        parsed,
        findings,
        valid_card_ids,
    )

    usage = response.usage
    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0

    return MergedFeedbackResult(
        document_id=factuality.document_id,
        model=selected_model,
        status=status,
        items=items,
        unchecked=tuple(unchecked),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        factuality=factuality,
        completeness=completeness,
    )
