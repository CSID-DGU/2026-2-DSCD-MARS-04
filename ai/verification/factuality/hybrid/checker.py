from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from ai.verification.factuality.hybrid.evidence_matcher import (
    match_evidence,
)
from ai.verification.factuality.hybrid.nli_checker import (
    NLIPredictor,
    check_nli,
    predict_nli,
)
from ai.verification.factuality.hybrid.rule_checks import (
    RiskFlag,
    check_rule_risks,
)
from ai.verification.shared.card_text_extractor import (
    extract_card_texts,
)
from data_pipeline.schemas.card import FinalCardOutput
from data_pipeline.schemas.group import Group

Status = Literal[
    "SUPPORTED",
    "POSSIBLE_DISTORTION",
    "INSUFFICIENT_EVIDENCE",
    "UNCERTAIN",
]


@dataclass(frozen=True)
class FieldCheckResult:
    unit_id: str
    card_id: str
    field_path: str
    text: str
    status: Status
    evidence_ids: tuple[str, ...]
    nli_labels: tuple[str, ...]
    risk_flags: tuple[RiskFlag, ...]


@dataclass(frozen=True)
class CardCheckResult:
    card_id: str
    group_id: str | None
    status: Status
    fields: tuple[FieldCheckResult, ...]


@dataclass(frozen=True)
class CompletenessResult:
    document_id: str
    status: Status
    cards: tuple[CardCheckResult, ...]


def combine_field_status(
    nli_labels: list[str],
    flags: list[RiskFlag],
    *,
    has_evidence: bool,
) -> Status:
    """Conservatively combine retrieval, NLI, and rule signals."""

    if not has_evidence:
        return "UNCERTAIN"

    valid_labels = [
        label for label in nli_labels if label in {"ENTAILMENT", "NEUTRAL", "CONTRADICTION"}
    ]

    if len(valid_labels) != len(nli_labels) or not valid_labels:
        return "UNCERTAIN"

    has_entailment = "ENTAILMENT" in valid_labels
    has_contradiction = "CONTRADICTION" in valid_labels

    # Conflicting evidence requires manual review.
    if has_entailment and has_contradiction:
        return "UNCERTAIN"

    # Risk flags indicate suspicion, not confirmed errors.
    if flags:
        return "POSSIBLE_DISTORTION"

    if has_entailment:
        return "SUPPORTED"

    if has_contradiction:
        return "POSSIBLE_DISTORTION"

    return "INSUFFICIENT_EVIDENCE"


def aggregate_status(statuses: list[Status]) -> Status:
    """Aggregate field/card statuses without masking issues."""

    if not statuses:
        return "UNCERTAIN"

    if "POSSIBLE_DISTORTION" in statuses:
        return "POSSIBLE_DISTORTION"

    if "INSUFFICIENT_EVIDENCE" in statuses:
        return "INSUFFICIENT_EVIDENCE"

    if "UNCERTAIN" in statuses:
        return "UNCERTAIN"

    return "SUPPORTED"


def check_completeness(
    groups: list[Group],
    final_cards: FinalCardOutput,
    *,
    predictor: NLIPredictor = predict_nli,
    top_k: int = 3,
) -> CompletenessResult:
    """Verify the latest card text against its group summaries."""

    group_ids = {group.group_id for group in groups}

    for card in final_cards.cards:
        if card.group_id is not None and card.group_id not in group_ids:
            raise ValueError(f"카드 {card.card_id}의 그룹 {card.group_id}이 검증 입력에 없습니다.")

    units = extract_card_texts(final_cards)
    matches = match_evidence(units, groups, top_k=top_k)

    fields_by_card = defaultdict(list)

    for match in matches:
        flags = check_rule_risks(match)
        nli = check_nli(match, predictor=predictor)

        labels = [result.label for result in nli.evidence_results]

        status = combine_field_status(
            labels,
            flags,
            has_evidence=bool(match.candidates),
        )

        field_result = FieldCheckResult(
            unit_id=match.unit.unit_id,
            card_id=match.unit.card_id,
            field_path=match.unit.field_path,
            text=match.unit.text,
            status=status,
            evidence_ids=tuple(item.evidence_id for item in nli.evidence_results),
            nli_labels=tuple(labels),
            risk_flags=tuple(flags),
        )

        fields_by_card[match.unit.card_id].append(field_result)

    card_results = []

    for card in final_cards.cards:
        fields = tuple(fields_by_card[card.card_id])

        # Cover and closing cards have no group-level evidence.
        if card.group_id is None:
            card_status: Status = "UNCERTAIN"
        else:
            card_status = aggregate_status([field.status for field in fields])

        card_results.append(
            CardCheckResult(
                card_id=card.card_id,
                group_id=card.group_id,
                status=card_status,
                fields=fields,
            )
        )

    overall = aggregate_status([card.status for card in card_results if card.group_id is not None])

    return CompletenessResult(
        document_id=final_cards.document_id,
        status=overall,
        cards=tuple(card_results),
    )
