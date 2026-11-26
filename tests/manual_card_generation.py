import json
from pathlib import Path

from ai.generation.card_generator import generate_cards
from ai.generation.layout_selector import select_layouts
from data_pipeline.schemas.group import Group

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "data" / "samples" / "news_014_analysis.json"
OUTPUT_PATH = ROOT / "data" / "samples" / "news_014_cards.json"


def main():
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    document_id = data["document_id"]

    groups = [
        Group(
            group_id=item["group_id"],
            sentence_ids=item["sentence_ids"],
            summary=item["summary"],
            topic=item.get("topic", ""),
            headline=item.get("headline", ""),
        )
        for item in data["groups"]
    ]

    layout_result = select_layouts(
        document_id=document_id,
        groups=groups,
    )

    print("=== 레이아웃 선택 결과 ===")
    print(layout_result.model_dump_json(indent=2))

    card_result = generate_cards(
        document_id=document_id,
        groups=groups,
        layout_selections=layout_result.layout_selections,
        include_boundary_cards=True,
    )

    print("=== 카드 문구 생성 결과 ===")
    print(card_result.model_dump_json(indent=2))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        card_result.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(f"생성 결과 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
