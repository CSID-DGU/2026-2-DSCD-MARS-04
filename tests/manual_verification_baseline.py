import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

from ai.verification.completeness.llm.llm_checker import check_llm_completeness
from ai.verification.factuality.llm.llm_checker import check_llm_factuality
from data_pipeline.schemas.card import FinalCardOutput
from data_pipeline.schemas.group import Group

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = ROOT / "data" / "samples" / "news_014_analysis.json"
CARDS_PATH = ROOT / "data" / "samples" / "news_014_cards.json"
OUTPUT_PATH = ROOT / "data" / "samples" / "news_014_baseline.json"


def to_jsonable(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, Enum):
        return to_jsonable(obj.value)

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, dict):
        return {str(key): to_jsonable(value) for key, value in obj.items()}

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(value) for value in obj]

    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump(mode="json"))

    if is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: to_jsonable(getattr(obj, field.name)) for field in fields(obj)}

    if hasattr(obj, "__dict__"):
        return {
            key: to_jsonable(value) for key, value in vars(obj).items() if not key.startswith("_")
        }

    raise TypeError(f"JSON으로 변환할 수 없는 자료형: {type(obj).__name__}")


def load_json(path):
    if not path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_result(result):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    serialized = json.dumps(
        to_jsonable(result),
        ensure_ascii=False,
        indent=2,
    )

    temp_path = OUTPUT_PATH.with_suffix(".json.tmp")

    temp_path.write_text(serialized, encoding="utf-8")
    temp_path.replace(OUTPUT_PATH)

    print(f"검증 결과 저장: {OUTPUT_PATH}")


def build_final_cards(cards_data):
    body_cards = []

    for index, card in enumerate(cards_data["cards"], start=1):
        if card["layout_id"] in ("cover", "closing"):
            continue

        if card.get("group_id") is None:
            raise ValueError(f"{index}번째 본문 카드에 group_id가 없습니다.")

        body_cards.append(
            {
                **card,
                "card_id": card.get("card_id") or f"C{index}",
            }
        )

    if not body_cards:
        raise ValueError("검증할 본문 카드가 없습니다.")

    return FinalCardOutput.model_validate(
        {
            "document_id": cards_data["document_id"],
            "cards": body_cards,
        }
    )


def print_result(title, data):
    print(f"\n=== {title} ===")

    print(
        json.dumps(
            to_jsonable(data),
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    analysis_data = load_json(ANALYSIS_PATH)
    cards_data = load_json(CARDS_PATH)

    document_id = analysis_data["document_id"]

    if document_id != cards_data["document_id"]:
        raise ValueError("분석 결과와 카드 생성 결과의 document_id가 일치하지 않습니다.")

    groups = [Group.model_validate(group) for group in analysis_data["groups"]]

    if not groups:
        raise ValueError("검증할 그룹이 없습니다.")

    final_cards = build_final_cards(cards_data)

    required_group_ids = [group.group_id for group in groups]

    result = {
        "document_id": document_id,
        "evaluation_type": "baseline",
        "factuality": None,
        "completeness": None,
    }

    print(f"문서 ID: {document_id}")
    print(f"그룹 수: {len(groups)}")
    print(f"본문 카드 수: {len(final_cards.cards)}")

    try:
        print("\n=== 사실성 검사 시작 ===")

        factuality = check_llm_factuality(
            groups=groups,
            final_cards=final_cards,
        )

        result["factuality"] = to_jsonable(factuality)
        save_result(result)
        print_result("사실성 검사 결과", factuality)

        print("\n=== 완전성 검사 시작 ===")

        completeness = check_llm_completeness(
            groups=groups,
            final_cards=final_cards,
            required_group_ids=required_group_ids,
        )

        result["completeness"] = to_jsonable(completeness)
        save_result(result)
        print_result("완전성 검사 결과", completeness)

    except Exception:
        save_result(result)
        raise

    print("\n=== 원본 검증 완료 ===")
    print(f"결과 파일: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
