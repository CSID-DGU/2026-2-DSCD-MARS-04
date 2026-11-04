from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ai.verification.factuality.hybrid.evidence_matcher import EvidenceMatch

MODEL_NAME = "Huffon/klue-roberta-base-nli"
LABELS = ("ENTAILMENT", "NEUTRAL", "CONTRADICTION")

NLIPredictor = Callable[[str, str], dict[str, float]]


@dataclass(frozen=True)
class NLIEvidenceResult:
    evidence_id: str
    evidence_text: str
    label: str
    scores: dict[str, float]
    status: str


@dataclass(frozen=True)
class NLICheckResult:
    unit_id: str
    card_id: str
    group_id: str
    field_path: str
    card_text: str
    evidence_results: tuple[NLIEvidenceResult, ...]


@lru_cache(maxsize=1)
def load_nli_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()

    return tokenizer, model


def predict_nli(
    premise: str,
    hypothesis: str,
) -> dict[str, float]:
    tokenizer, model = load_nli_model()

    inputs = tokenizer(
        premise,
        hypothesis,
        return_tensors="pt",
        truncation=False,
        return_token_type_ids=False,
    )

    inputs.pop("token_type_ids", None)

    max_length = min(
        tokenizer.model_max_length,
        model.config.max_position_embeddings - 2,
    )

    if inputs["input_ids"].shape[1] > max_length:
        raise ValueError("NLI 입력 길이가 모델 제한을 초과했습니다.")

    with torch.inference_mode():
        logits = model(**inputs).logits
        probabilities = torch.softmax(logits, dim=-1)[0]

    scores = {
        model.config.id2label[index].upper(): float(prob.item())
        for index, prob in enumerate(probabilities)
    }

    if set(scores) != set(LABELS):
        raise ValueError(f"예상하지 못한 NLI 레이블: {scores}")

    return scores


def check_nli(
    match: EvidenceMatch,
    *,
    predictor: NLIPredictor = predict_nli,
) -> NLICheckResult:
    evidence_results = []

    for candidate in match.candidates:
        premise = candidate.evidence.text
        hypothesis = match.unit.context

        try:
            scores = predictor(premise, hypothesis)

            if set(scores) != set(LABELS):
                raise ValueError("NLI 레이블 구성이 잘못되었습니다.")

            label = max(scores, key=scores.get)
            status = "OK"

        except ValueError:
            scores = {}
            label = "UNAVAILABLE"
            status = "INPUT_ERROR"

        evidence_results.append(
            NLIEvidenceResult(
                evidence_id=candidate.evidence.evidence_id,
                evidence_text=premise,
                label=label,
                scores=scores,
                status=status,
            )
        )

    return NLICheckResult(
        unit_id=match.unit.unit_id,
        card_id=match.unit.card_id,
        group_id=match.unit.group_id,
        field_path=match.unit.field_path,
        card_text=match.unit.text,
        evidence_results=tuple(evidence_results),
    )


def check_all_nli(
    matches: list[EvidenceMatch],
    *,
    predictor: NLIPredictor = predict_nli,
) -> list[NLICheckResult]:
    return [check_nli(match, predictor=predictor) for match in matches]
