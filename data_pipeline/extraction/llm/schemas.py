from dataclasses import dataclass, field


@dataclass
class Sentence:
    sentence_id: str
    text: str


@dataclass
class VerificationResult:
    status: str
    retry_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class KeySentence:
    key_id: str
    source_sentence_ids: list[str]
    original_text: str
    summary: str
    verification: VerificationResult


@dataclass
class ExtractionResult:
    document_id: str
    key_sentences: list[KeySentence]
