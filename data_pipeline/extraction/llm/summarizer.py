import json

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()


def summarize_key_sentences(
    sentences: list[dict],
    selected_ids: list[str],
) -> list[dict]:
    sentence_map = {sentence["sentence_id"]: sentence["text"] for sentence in sentences}

    selected_sentences = [
        {
            "sentence_id": sentence_id,
            "text": sentence_map[sentence_id],
        }
        for sentence_id in selected_ids
    ]

    formatted_sentences = "\n".join(
        f"[{sentence['sentence_id']}] {sentence['text']}" for sentence in selected_sentences
    )

    prompt = f"""
당신은 카드뉴스에 사용할 한국어 핵심 문장을 요약하는 시스템입니다.

입력된 각 문장을 짧고 읽기 쉽게 요약하세요.

규칙:
1. 각 원문을 한 개의 짧은 문장 또는 구 형태로 요약하세요.
2. 원문에 없는 정보를 추가하지 마세요.
3. 숫자, 날짜, 금액, 인원, 대상, 장소를 변경하지 마세요.
4. '최대', '최소', '이상', '이하', '약', '예정', '가능성' 같은
   한정 및 확실성 표현을 보존하세요.
5. 중요한 조건이나 예외를 제거해 의미를 바꾸지 마세요.
6. 문장의 핵심 주체와 행동을 유지하세요.
7. sentence_id를 변경하지 마세요.
8. 설명 없이 아래 JSON 형식으로만 반환하세요.

{{
  "summaries": [
    {{
      "sentence_id": "S1",
      "summary": "요약문"
    }}
  ]
}}

요약할 문장:
{formatted_sentences}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    result = json.loads(response.output_text)
    summaries = result["summaries"]

    validate_summaries(selected_ids, summaries)

    return summaries


def validate_summaries(
    selected_ids: list[str],
    summaries: list[dict],
) -> None:
    returned_ids = [item["sentence_id"] for item in summaries]

    if len(summaries) != len(selected_ids):
        raise ValueError("선택한 문장 수와 요약문 수가 다릅니다.")

    if set(returned_ids) != set(selected_ids):
        raise ValueError(f"요약문 ID가 선택된 ID와 다릅니다: {returned_ids}")

    for item in summaries:
        summary = item.get("summary", "")

        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"빈 요약문이 있습니다: {item}")
