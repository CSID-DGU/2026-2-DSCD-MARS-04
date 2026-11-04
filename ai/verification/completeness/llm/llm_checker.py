
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from data_pipeline.schemas.card import Card, FinalCardOutput
from data_pipeline.schemas.group import Group

load_dotenv()

DEFAULT_MODEL = "gpt-4.1-mini"

CoverageStatus = Literal[
    "COVERED",
    "PARTIALLY_COVERED",
    "MISSING",
    "DISTORTED",
    "UNCERTAIN",
]

CheckStatus = CoverageStatus | Literal["NOT_CHECKED"]


class RequiredFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    group_id: str
    text: str


class FactJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    status: CoverageStatus
    matched_card_ids: list[str]
    reason: str
    missing_elements: list[str]


class CoverageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[FactJudgment]


@dataclass(frozen=True)
class CompletenessResult:
    document_id: str
    model: str
    status: CheckStatus
    results: tuple[FactJudgment, ...]
    input_tokens: int
    output_tokens: int


@lru_cache(maxsize=1)
def load_completeness_prompt() -> str:
    path = Path(__file__).with_name("c_prompt.md")

    if not path.is_file():
        raise FileNotFoundError(
            f"완전성 검사 프롬프트를 찾을 수 없습니다: {path}"
        )

    prompt = path.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError("완전성 검사 프롬프트가 비어 있습니다.")

    return prompt


def build_required_facts(
    groups: list[Group],
    required_group_ids: list[str] | None = None,
) -> list[RequiredFact]:
    group_map = {group.group_id: group for group in groups}

    if len(group_map) != len(groups):
        raise ValueError("그룹 ID가 중복되었습니다.")

    if required_group_ids is None:
        selected_groups = groups
    else:
        if len(required_group_ids) != len(set(required_group_ids)):
            raise ValueError("선택한 그룹 ID가 중복되었습니다.")

        unknown_ids = set(required_group_ids) - set(group_map)

        if unknown_ids:
            raise ValueError(
                f"존재하지 않는 그룹 ID: {sorted(unknown_ids)}"
            )

        selected_groups = [
            group_map[group_id]
            for group_id in required_group_ids
        ]

    required_facts = []

    for group in selected_groups:
        summary = group.summary.strip()

        if not summary:
            raise ValueError(
                f"{group.group_id}의 summary가 비어 있습니다."
            )

        required_facts.append(
            RequiredFact(
                fact_id=f"{group.group_id}:summary",
                group_id=group.group_id,
                text=summary,
            )
        )

    return required_facts


def aggregate_status(
    statuses: list[CoverageStatus],
) -> CheckStatus:
    if not statuses:
        return "NOT_CHECKED"

    if "DISTORTED" in statuses:
        return "DISTORTED"

    if "MISSING" in statuses:
        return "MISSING"

    if "PARTIALLY_COVERED" in statuses:
        return "PARTIALLY_COVERED"

    if "UNCERTAIN" in statuses:
        return "UNCERTAIN"

    return "COVERED"


def extract_card_content(card: Card) -> dict:
    data = card.model_dump(mode="json")

    return {
        "card_id": data["card_id"],
        "layout_id": data["layout_id"],
        "title": data.get("title"),
        "body": data.get("body"),
        "items": data.get("items"),
        "left": data.get("left"),
        "right": data.get("right"),
        "cta": data.get("cta"),
    }


def make_missing_judgments(
    required_facts: list[RequiredFact],
) -> list[FactJudgment]:
    return [
        FactJudgment(
            fact_id=fact.fact_id,
            status="MISSING",
            matched_card_ids=[],
            reason="선택된 그룹에 연결된 생성 카드가 없습니다.",
            missing_elements=[fact.text],
        )
        for fact in required_facts
    ]


def validate_coverage_response(
    parsed: CoverageResponse,
    required_facts: list[RequiredFact],
    cards: list[Card],
) -> list[FactJudgment]:
    expected_ids = [fact.fact_id for fact in required_facts]
    returned_ids = [result.fact_id for result in parsed.results]

    if (
        len(returned_ids) != len(expected_ids)
        or set(returned_ids) != set(expected_ids)
    ):
        raise ValueError(
            "LLM이 반환한 검증 항목 ID가 요청한 ID와 일치하지 않습니다."
        )

    valid_card_ids = {card.card_id for card in cards}

    for result in parsed.results:
        if len(result.matched_card_ids) != len(
            set(result.matched_card_ids)
        ):
            raise ValueError(
                f"{result.fact_id}: 카드 ID가 중복되었습니다."
            )

        if not set(result.matched_card_ids).issubset(valid_card_ids):
            raise ValueError(
                f"{result.fact_id}에 존재하지 않는 카드 ID가 포함되어 있습니다."
            )

        if result.status == "MISSING" and result.matched_card_ids:
            raise ValueError(
                f"{result.fact_id}: 누락된 정보에 관련 카드가 지정되었습니다."
            )

        if result.status == "COVERED" and result.missing_elements:
            raise ValueError(
                f"{result.fact_id}: 반영 완료 정보에 누락 요소가 있습니다."
            )

    result_map = {
        result.fact_id: result
        for result in parsed.results
    }

    return [
        result_map[fact_id]
        for fact_id in expected_ids
    ]


def verify_group_coverage(
    group: Group,
    required_facts: list[RequiredFact],
    cards: list[Card],
    *,
    client: OpenAI | None,
    model: str,
) -> tuple[list[FactJudgment], int, int]:
    if not cards:
        return make_missing_judgments(required_facts), 0, 0

    if client is None:
        raise ValueError("OpenAI 클라이언트가 필요합니다.")

    payload = {
        "group_id": group.group_id,
        "evidence_summary": group.summary,
        "required_facts": [
            fact.model_dump(mode="json")
            for fact in required_facts
        ],
        "cards": [
            extract_card_content(card)
            for card in cards
        ],
    }

    response = client.responses.parse(
        model=model,
        instructions=load_completeness_prompt(),
        input=json.dumps(payload, ensure_ascii=False),
        text_format=CoverageResponse,
        store=False,
    )

    parsed = response.output_parsed

    if parsed is None:
        raise ValueError(
            f"{group.group_id}의 완전성 검사 결과를 파싱하지 못했습니다."
        )

    judgments = validate_coverage_response(
        parsed=parsed,
        required_facts=required_facts,
        cards=cards,
    )

    usage = response.usage

    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0

    return judgments, input_tokens, output_tokens


def check_llm_completeness(
    groups: list[Group],
    final_cards: FinalCardOutput,
    required_facts: list[RequiredFact] | None = None,
    *,
    required_group_ids: list[str] | None = None,
    model: str | None = None,
    client: OpenAI | None = None,
) -> CompletenessResult:
    selected_model = (
        model
        or os.getenv("VERIFICATION_MODEL")
        or DEFAULT_MODEL
    )

    group_map = {
        group.group_id: group
        for group in groups
    }

    if len(group_map) != len(groups):
        raise ValueError("그룹 ID가 중복되었습니다.")

    if required_facts is None:
        required_facts = build_required_facts(
            groups=groups,
            required_group_ids=required_group_ids,
        )
    elif required_group_ids is not None:
        raise ValueError(
            "required_facts와 required_group_ids는 함께 지정할 수 없습니다."
        )

    fact_ids = [
        fact.fact_id
        for fact in required_facts
    ]

    if len(fact_ids) != len(set(fact_ids)):
        raise ValueError("검증 항목 ID가 중복되었습니다.")

    for fact in required_facts:
        if fact.group_id not in group_map:
            raise ValueError(
                f"{fact.fact_id}의 그룹 {fact.group_id}이 존재하지 않습니다."
            )

        if not fact.text.strip():
            raise ValueError(
                f"{fact.fact_id}의 검증 내용이 비어 있습니다."
            )

    card_ids = [
        card.card_id
        for card in final_cards.cards
    ]

    if len(card_ids) != len(set(card_ids)):
        raise ValueError("카드 ID가 중복되었습니다.")

    if not required_facts:
        return CompletenessResult(
            document_id=final_cards.document_id,
            model=selected_model,
            status="NOT_CHECKED",
            results=(),
            input_tokens=0,
            output_tokens=0,
        )

    facts_by_group: dict[str, list[RequiredFact]] = {}

    for fact in required_facts:
        facts_by_group.setdefault(
            fact.group_id,
            [],
        ).append(fact)

    cards_by_group: dict[str, list[Card]] = {}

    for card in final_cards.cards:
        if card.group_id is not None:
            cards_by_group.setdefault(
                card.group_id,
                [],
            ).append(card)

    needs_api = any(
        cards_by_group.get(group_id)
        for group_id in facts_by_group
    )

    if needs_api and client is None:
        client = OpenAI()

    results: list[FactJudgment] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for group_id, group_facts in facts_by_group.items():
        judgments, input_tokens, output_tokens = (
            verify_group_coverage(
                group=group_map[group_id],
                required_facts=group_facts,
                cards=cards_by_group.get(group_id, []),
                client=client,
                model=selected_model,
            )
        )

        results.extend(judgments)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

    return CompletenessResult(
        document_id=final_cards.document_id,
        model=selected_model,
        status=aggregate_status(
            [result.status for result in results]
        ),
        results=tuple(results),
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
    )
