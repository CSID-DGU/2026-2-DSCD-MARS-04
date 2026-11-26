import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from ai.generation.card_generator import generate_cards
from ai.generation.group_merger import merge_group_results
from ai.generation.group_selector import select_groups
from ai.generation.group_titles import generate_group_titles
from ai.generation.layout_selector import select_layouts
from ai.verification.completeness.llm.llm_checker import (
    build_required_facts,
    check_llm_completeness,
)
from ai.verification.factuality.llm.llm_checker import check_llm_factuality
from ai.verification.feedback.merger import merge_feedback
from data_pipeline.schemas.card import Card, FinalCardOutput
from data_pipeline.schemas.group import (
    GroupAnalysisOutput,
    GroupPresentationOutput,
    GroupSelectionOutput,
)


def save_result(destination: Path, name: str, value) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    payload = TypeAdapter(type(value)).dump_python(value, mode="json")
    (destination / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_pipeline(
    analysis: GroupAnalysisOutput,
    selection: GroupSelectionOutput,
    output_dir: Path,
    *,
    client=None,
):
    if analysis.document_id != selection.document_id:
        raise ValueError("분석 결과와 선택 결과의 document_id가 다릅니다.")
    ids = selection.required_group_ids
    group_ids = [group.group_id for group in analysis.groups]
    if not ids or len(ids) != len(set(ids)) or not set(ids).issubset(group_ids):
        raise ValueError("유효한 정보 묶음을 하나 이상 선택해야 합니다.")
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("분석 결과의 그룹 ID가 중복되었습니다.")
    selected_analysis = GroupAnalysisOutput(
        document_id=analysis.document_id,
        groups=[next(g for g in analysis.groups if g.group_id == gid) for gid in ids],
    )
    save_result(output_dir, "analysis", analysis)
    save_result(output_dir, "selection", selection)
    print("그룹 제목 생성", flush=True)
    titles = generate_group_titles(
        selected_analysis.model_dump(),
        client=client,
        log_path=output_dir / "titles.jsonl",
    )
    groups = merge_group_results(
        selected_analysis, GroupPresentationOutput.model_validate(titles.model_dump())
    )
    groups = select_groups(groups, ids)
    save_result(output_dir, "selected_groups", groups)
    required_facts = build_required_facts(groups)
    save_result(output_dir, "required_facts", required_facts)
    print("레이아웃 선택", flush=True)
    layouts = select_layouts(
        analysis.document_id,
        groups,
        client=client,
        log_path=output_dir / "layouts.jsonl",
    )
    save_result(output_dir, "layouts", layouts)
    print("기존 Generation 실행", flush=True)
    generated = generate_cards(
        analysis.document_id,
        groups,
        layouts.layout_selections,
        client=client,
        log_path=output_dir / "generation.jsonl",
        include_boundary_cards=True,
    )
    save_result(output_dir, "generation", generated)
    final_cards = FinalCardOutput(
        document_id=generated.document_id,
        cards=[
            Card(card_id=f"C{index}", **card.model_dump())
            for index, card in enumerate(generated.cards, start=1)
        ],
    )
    save_result(output_dir, "final_cards", final_cards)
    print("LLM 사실성 검사", flush=True)
    factuality = check_llm_factuality(groups, final_cards, client=client)
    save_result(output_dir, "factuality", factuality)
    print("LLM 완전성 검사", flush=True)
    completeness = check_llm_completeness(groups, final_cards, client=client)
    save_result(output_dir, "completeness", completeness)
    print("피드백 병합", flush=True)
    feedback = merge_feedback(factuality, completeness, client=client)
    save_result(output_dir, "feedback", feedback)
    print(
        f"완료: {len(final_cards.cards)}장 / 사실성 {factuality.status} / "
        f"완전성 {completeness.status} / 피드백 {feedback.status}",
        flush=True,
    )
    return feedback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_pipeline(
        GroupAnalysisOutput.model_validate_json(args.analysis.read_text(encoding="utf-8")),
        GroupSelectionOutput.model_validate_json(args.selection.read_text(encoding="utf-8")),
        args.output_dir,
    )


if __name__ == "__main__":
    main()
