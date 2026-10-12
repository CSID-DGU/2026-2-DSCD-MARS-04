import json

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI()


def extract_key_sentences(sentences: list[dict]) -> list[str]:
    formatted_sentences = "\n".join(
        f"[{sentence['sentence_id']}] {sentence['text']}"
        for sentence in sentences
    )

    prompt = f"""
당신은 한국어 뉴스 기사에서 핵심 문장을 선택하는 시스템입니다.

다음 규칙을 지키세요.

1. 기사의 핵심 사건, 결정, 결과를 전달하는 문장 3~5개를 선택하세요.
2. 중요한 수치, 대상, 조건, 기간, 예외, 불확실성이 담긴 문장을 고려하세요.
3. 배경 설명, 반복 표현, 단순 인터뷰 소감은 우선순위를 낮추세요.
4. 새로운 문장을 작성하지 마세요.
5. 반드시 입력에 존재하는 sentence_id만 선택하세요.
6. 결과는 설명 없이 아래 JSON 형식으로만 반환하세요.

{{
  "key_sentence_ids": ["S1", "S2", "S3"]
}}

뉴스 기사:
{formatted_sentences}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    result = json.loads(response.output_text)
    selected_ids = result["key_sentence_ids"]

    validate_selected_ids(sentences, selected_ids)

    return selected_ids


def validate_selected_ids(
    sentences: list[dict],
    selected_ids: list[str],
) -> None:
    valid_ids = {
        sentence["sentence_id"]
        for sentence in sentences
    }

    if not 3 <= len(selected_ids) <= 5:
        raise ValueError(
            f"핵심 문장은 3~5개여야 합니다: {selected_ids}"
        )

    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError(
            f"중복된 문장 ID가 있습니다: {selected_ids}"
        )

    invalid_ids = [
        sentence_id
        for sentence_id in selected_ids
        if sentence_id not in valid_ids
    ]

    if invalid_ids:
        raise ValueError(
            f"존재하지 않는 문장 ID입니다: {invalid_ids}"
        )