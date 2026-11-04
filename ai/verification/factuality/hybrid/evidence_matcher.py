
import re
from dataclasses import dataclass
from functools import lru_cache

from kiwipiepy import Kiwi

from ai.verification.shared.card_text_extractor import CardTextUnit
from data_pipeline.schemas.group import Group

NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")

CONTENT_TAGS = {
    "NNG",
    "NNP",
    "NNB",
    "NR",
    "SL",
    "SH",
    "SN",
    "VV",
    "VA",
    "XR",
}

STOPWORDS = {
    "것",
    "수",
    "등",
    "경우",
    "관련",
    "내용",
    "정보",
    "이번",
    "해당",
}


@dataclass(frozen=True)
class EvidenceSentence:
    evidence_id: str
    group_id: str
    text: str


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence: EvidenceSentence
    score: float


@dataclass(frozen=True)
class EvidenceMatch:
    unit: CardTextUnit
    candidates: tuple[EvidenceCandidate, ...]


@lru_cache(maxsize=1)
def get_kiwi() -> Kiwi:
    return Kiwi()


def split_group_summary(group: Group) -> list[EvidenceSentence]:
    summary = group.summary.strip()

    if not summary:
        return []

    sentences = get_kiwi().split_into_sents(summary)

    return [
        EvidenceSentence(
            evidence_id=f"{group.group_id}_E{index}",
            group_id=group.group_id,
            text=summary[sentence.start : sentence.end].strip(),
        )
        for index, sentence in enumerate(sentences, start=1)
        if summary[sentence.start : sentence.end].strip()
    ]


@lru_cache(maxsize=4096)
def extract_keywords(text: str) -> frozenset[str]:
    keywords = {
        token.form.lower()
        for token in get_kiwi().tokenize(text)
        if token.tag in CONTENT_TAGS
        and len(token.form.strip()) > 1
        and token.form.lower() not in STOPWORDS
    }

    keywords.update(
        number.replace(",", "")
        for number in NUMBER_PATTERN.findall(text)
    )

    return frozenset(keywords)


def calculate_similarity(
    query: str,
    evidence: str,
) -> float:
    query_words = extract_keywords(query)
    evidence_words = extract_keywords(evidence)

    if not query_words or not evidence_words:
        return 0.0

    shared = query_words & evidence_words

    if not shared:
        return 0.0

    recall = len(shared) / len(query_words)
    precision = len(shared) / len(evidence_words)

    score = 0.8 * recall + 0.2 * precision

    return round(score, 4)


def match_evidence(
    units: list[CardTextUnit],
    groups: list[Group],
    *,
    top_k: int = 3,
    min_score: float = 0.15,
) -> list[EvidenceMatch]:
    if top_k < 1:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    if not 0 <= min_score <= 1:
        raise ValueError("min_score는 0~1 범위여야 합니다.")

    evidence_by_group = {
        group.group_id: split_group_summary(group)
        for group in groups
    }

    results = []

    for unit in units:
        evidence_sentences = evidence_by_group.get(
            unit.group_id,
            [],
        )

        candidates = []

        for evidence in evidence_sentences:
            score = calculate_similarity(
                unit.context,
                evidence.text,
            )

            if score >= min_score:
                candidates.append(
                    EvidenceCandidate(
                        evidence=evidence,
                        score=score,
                    )
                )

        candidates.sort(
            key=lambda item: item.score,
            reverse=True,
        )

        results.append(
            EvidenceMatch(
                unit=unit,
                candidates=tuple(candidates[:top_k]),
            )
        )

    return results
