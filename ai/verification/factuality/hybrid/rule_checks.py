"""Detect numeric and qualifier risks in card text."""

import re
from dataclasses import dataclass
from decimal import Decimal

from ai.verification.factuality.hybrid.evidence_matcher import EvidenceMatch

MEASURE_PATTERN = re.compile(
    r"(?<![\d.])"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"\s*"
    r"(?P<unit>%대|%|만원|억원|천원|원|개월|년|월|일|"
    r"명|대|건|가구|세|개)"
)

QUALIFIER_PATTERN = re.compile(r"최대|최소|이상|이하|초과|미만|약|대략")

CLAUSE_BOUNDARY = re.compile(r"[,，;；.!?\n]")

SUBJECT_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z]+")

SUBJECT_STOPWORDS = {
    "최대",
    "최소",
    "이상",
    "이하",
    "초과",
    "미만",
    "약",
    "대략",
    "총",
    "올해",
    "보조금",
    "지원금",
    "금액",
    "지급",
    "지원",
    "적용",
    "혜택",
}

SUBJECT_PARTICLES = (
    "으로는",
    "에서는",
    "에게는",
    "으로",
    "에서",
    "에게",
    "에는",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "도",
)


@dataclass(frozen=True)
class Measurement:
    value: Decimal
    unit: str
    qualifier: str | None
    text: str


@dataclass(frozen=True)
class RiskFlag:
    unit_id: str
    card_id: str
    group_id: str
    field_path: str
    risk_type: str
    card_text: str
    evidence_text: str
    detail: str


@dataclass(frozen=True)
class MeasurementRelation:
    """A measurement and its nearby subject description."""

    measurement: Measurement
    subject_tokens: frozenset[str]


def normalize_measure(
    number: str,
    unit: str,
) -> tuple[Decimal, str]:
    """Normalize equivalent numeric expressions."""

    value = Decimal(number.replace(",", ""))

    if unit == "만원":
        return value * 10000, "원"

    if unit == "억원":
        return value * 100000000, "원"

    if unit == "천원":
        return value * 1000, "원"

    return value, unit


def get_clause_prefix(text: str, number_start: int) -> str:
    """Return the clause preceding a numeric expression."""

    clause_start = 0

    for index, char in enumerate(text[:number_start]):
        if char not in ",，;；.!?\n":
            continue

        previous = text[index - 1] if index > 0 else ""
        following = text[index + 1] if index + 1 < len(text) else ""

        # Keep decimal points and thousands separators intact.
        if char in ",." and previous.isdigit() and following.isdigit():
            continue

        clause_start = index + 1

    return text[clause_start:number_start].strip()


def extract_qualifier(prefix: str) -> str | None:
    """Find the closest qualifier before a measurement."""

    qualifiers = list(QUALIFIER_PATTERN.finditer(prefix[-12:]))

    if not qualifiers:
        return None

    return qualifiers[-1].group()


def extract_measurements(text: str) -> list[Measurement]:
    """Extract explicit measurements and nearby qualifiers."""

    measurements = []

    for match in MEASURE_PATTERN.finditer(text):
        value, unit = normalize_measure(
            match.group("number"),
            match.group("unit"),
        )

        prefix = get_clause_prefix(text, match.start())

        measurements.append(
            Measurement(
                value=value,
                unit=unit,
                qualifier=extract_qualifier(prefix),
                text=match.group(),
            )
        )

    return measurements


def extract_subject_tokens(
    text: str,
    number_start: int,
) -> frozenset[str]:
    """Extract candidate subject words near a measurement."""

    prefix = get_clause_prefix(text, number_start)

    tokens = []

    for raw_token in SUBJECT_TOKEN_PATTERN.findall(prefix):
        token = raw_token

        for particle in SUBJECT_PARTICLES:
            if token.endswith(particle) and len(token) > len(particle):
                token = token[: -len(particle)]
                break

        token = token.casefold()

        if token and token not in SUBJECT_STOPWORDS:
            tokens.append(token)

    return frozenset(tokens)


def extract_measurement_relations(
    text: str,
) -> list[MeasurementRelation]:
    """Connect each numeric expression to nearby subject tokens."""

    measurements = extract_measurements(text)
    numeric_matches = list(MEASURE_PATTERN.finditer(text))

    relations = []

    for measurement, numeric_match in zip(
        measurements,
        numeric_matches,
        strict=True,
    ):
        relations.append(
            MeasurementRelation(
                measurement=measurement,
                subject_tokens=extract_subject_tokens(
                    text,
                    numeric_match.start(),
                ),
            )
        )

    return relations


def subject_similarity(
    card_tokens: frozenset[str],
    evidence_tokens: frozenset[str],
) -> float:
    """Calculate lexical similarity between subject descriptions."""

    if not card_tokens or not evidence_tokens:
        return 0.0

    intersection = card_tokens & evidence_tokens

    if not intersection:
        return 0.0

    return len(intersection) / len(card_tokens | evidence_tokens)


def make_flag(
    match: EvidenceMatch,
    risk_type: str,
    evidence_text: str,
    detail: str,
) -> RiskFlag:
    """Create a risk flag linked to a card text unit."""

    unit = match.unit

    return RiskFlag(
        unit_id=unit.unit_id,
        card_id=unit.card_id,
        group_id=unit.group_id,
        field_path=unit.field_path,
        risk_type=risk_type,
        card_text=unit.text,
        evidence_text=evidence_text,
        detail=detail,
    )


def select_evidence_measurements(
    card_relation: MeasurementRelation,
    evidence_data: list[tuple[str, list[MeasurementRelation]]],
) -> list[tuple[str, Measurement]]:
    """Select measurements with compatible units and subjects."""

    compatible = [
        (evidence_text, relation)
        for evidence_text, relations in evidence_data
        for relation in relations
        if relation.measurement.unit == card_relation.measurement.unit
    ]

    if not compatible:
        return []

    scored = [
        (
            subject_similarity(
                card_relation.subject_tokens,
                relation.subject_tokens,
            ),
            evidence_text,
            relation,
        )
        for evidence_text, relation in compatible
    ]

    best_score = max(score for score, _, _ in scored)

    if best_score > 0:
        return [
            (evidence_text, relation.measurement)
            for score, evidence_text, relation in scored
            if score == best_score
        ]

    # If neither side has a subject, comparing one
    # unique same-unit measurement is permissible.
    if (
        len(compatible) == 1
        and not card_relation.subject_tokens
        and not compatible[0][1].subject_tokens
    ):
        evidence_text, relation = compatible[0]

        return [(evidence_text, relation.measurement)]

    # Ambiguous subjects: do not choose a random amount.
    return []


def check_rule_risks(
    match: EvidenceMatch,
) -> list[RiskFlag]:
    """Compare card numbers with subject-matched evidence."""

    if not match.candidates:
        return []

    card_relations = extract_measurement_relations(match.unit.text)

    if not card_relations:
        return []

    evidence_data = [
        (
            candidate.evidence.text,
            extract_measurement_relations(candidate.evidence.text),
        )
        for candidate in match.candidates
    ]

    flags = []

    for card_relation in card_relations:
        card_measure = card_relation.measurement

        selected = select_evidence_measurements(
            card_relation,
            evidence_data,
        )

        if not selected:
            continue

        exact_matches = [
            (text, measure) for text, measure in selected if measure.value == card_measure.value
        ]

        if exact_matches:
            qualifier_matches = [
                (text, measure)
                for text, measure in exact_matches
                if measure.qualifier == card_measure.qualifier
            ]

            if qualifier_matches:
                continue

            evidence_text, evidence_measure = exact_matches[0]

            flags.append(
                make_flag(
                    match,
                    "QUALIFIER_MISMATCH",
                    evidence_text,
                    (
                        f"카드: {card_measure.text} "
                        f"({card_measure.qualifier or '한정 없음'}) / "
                        f"근거: {evidence_measure.text} "
                        f"({evidence_measure.qualifier or '한정 없음'})"
                    ),
                )
            )
            continue

        different_values = {measure.value for _, measure in selected}

        # Different equally relevant subjects can be ambiguous.
        if len(different_values) != 1:
            continue

        evidence_text, evidence_measure = selected[0]

        flags.append(
            make_flag(
                match,
                "NUMBER_MISMATCH",
                evidence_text,
                (
                    f"카드 수치 {card_measure.text}와 "
                    f"동일 대상의 근거 수치 "
                    f"{evidence_measure.text}가 다릅니다. "
                    "대상 연결 및 수치 확인이 필요합니다."
                ),
            )
        )

    return flags


def check_all_rule_risks(
    matches: list[EvidenceMatch],
) -> list[RiskFlag]:
    """Collect rule-based risk flags for all card units."""

    return [flag for match in matches for flag in check_rule_risks(match)]
