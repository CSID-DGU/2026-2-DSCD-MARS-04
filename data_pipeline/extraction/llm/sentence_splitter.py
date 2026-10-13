import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[dict]:
    normalized_text = normalize_text(text)

    parts = re.split(r"(?<=[.!?])\s+", normalized_text)
    parts = [part.strip() for part in parts if part.strip()]

    return [
        {
            "sentence_id": f"S{index}",
            "text": sentence,
        }
        for index, sentence in enumerate(parts, start=1)
    ]
