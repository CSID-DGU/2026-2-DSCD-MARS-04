from collections import Counter

from data_pipeline.schemas.card import (
    CardGenerationInput,
    CardGenerationOutput,
)

BODY_LAYOUTS = {"body", "compare", "checklist", "steps"}
LAYOUT_FIELDS = {"category", "body", "items", "left", "right", "cta"}


def validate_input(request: CardGenerationInput) -> None:
    """Validate groups and their selected layouts before an API call."""

    if not request.document_id.strip():
        raise ValueError("document_id가 비어 있습니다.")

    if not request.groups:
        raise ValueError("카드를 생성할 그룹이 없습니다.")

    group_ids = [group.group_id for group in request.groups]
    selection_ids = [selection.group_id for selection in request.layout_selections]
    layout_ids = [option.layout_id for option in request.available_layouts]

    if len(group_ids) != len(set(group_ids)):
        raise ValueError("입력 group_id가 중복되었습니다.")

    if len(selection_ids) != len(set(selection_ids)):
        raise ValueError("레이아웃 선택 group_id가 중복되었습니다.")

    if len(layout_ids) != len(set(layout_ids)):
        raise ValueError("레이아웃 정의 layout_id가 중복되었습니다.")

    if group_ids != selection_ids:
        raise ValueError("그룹과 레이아웃 선택 ID·순서가 일치하지 않습니다.")

    option_map = {option.layout_id: option for option in request.available_layouts}

    for group, selection in zip(
        request.groups,
        request.layout_selections,
        strict=True,
    ):
        if not group.group_id.strip() or not group.summary.strip():
            raise ValueError("group_id와 summary는 비어 있을 수 없습니다.")

        if not group.sentence_ids:
            raise ValueError(f"{group.group_id}: 근거 문장 ID가 없습니다.")

        if any(not sid.strip() for sid in group.sentence_ids):
            raise ValueError(f"{group.group_id}: 빈 문장 ID가 있습니다.")

        if len(group.sentence_ids) != len(set(group.sentence_ids)):
            raise ValueError(f"{group.group_id}: 문장 ID가 중복되었습니다.")

        if selection.layout_id not in BODY_LAYOUTS:
            raise ValueError(
                f"{group.group_id}: 본문 카드에 사용할 수 없는 레이아웃 {selection.layout_id}"
            )

        if selection.layout_id not in option_map:
            raise ValueError(f"{group.group_id}: 정의되지 않은 레이아웃 {selection.layout_id}")

        if not option_map[selection.layout_id].fields:
            raise ValueError(f"{group.group_id}: 레이아웃 필드 정의가 없습니다.")


def validate_output(
    request: CardGenerationInput,
    result: CardGenerationOutput,
) -> None:
    """Validate generated cards against layouts.json constraints."""

    if result.document_id != request.document_id:
        raise ValueError("출력 document_id가 입력과 다릅니다.")

    group_map = {group.group_id: group for group in request.groups}
    selection_map = {
        selection.group_id: selection.layout_id for selection in request.layout_selections
    }
    option_map = {option.layout_id: option for option in request.available_layouts}

    expected_order = [group.group_id for group in request.groups]
    actual_order = [card.group_id for card in result.cards]

    if any(group_id not in group_map for group_id in actual_order):
        raise ValueError("출력에 선택하지 않은 그룹이 포함되었습니다.")

    # 같은 그룹의 카드가 중간에 다른 그룹을 끼우지 않도록 검사
    actual_unique_order = []
    previous_group_id = None

    for group_id in actual_order:
        if group_id != previous_group_id:
            actual_unique_order.append(group_id)
            previous_group_id = group_id

    if actual_unique_order != expected_order:
        raise ValueError("출력 그룹 ID 또는 카드 순서가 일치하지 않습니다.")

    counts = Counter(actual_order)

    for group_id in expected_order:
        if not 1 <= counts[group_id] <= 2:
            raise ValueError(f"{group_id}: 그룹당 카드는 1~2장이어야 합니다.")

    for card in result.cards:
        group_id = card.group_id
        group = group_map[group_id]
        expected_layout = selection_map[group_id]

        if card.layout_id != expected_layout:
            raise ValueError(
                f"{group_id}: 선택된 레이아웃 {expected_layout}과 "
                f"출력 레이아웃 {card.layout_id}이 다릅니다."
            )

        if not card.sids:
            raise ValueError(f"{group_id}: 근거 문장 ID가 없습니다.")

        if len(card.sids) != len(set(card.sids)):
            raise ValueError(f"{group_id}: 근거 문장 ID가 중복되었습니다.")

        if not set(card.sids).issubset(set(group.sentence_ids)):
            raise ValueError(f"{group_id}: 해당 그룹에 없는 문장 ID가 포함되었습니다.")

        if not card.image_query.strip():
            raise ValueError(f"{group_id}: 이미지 검색어가 비어 있습니다.")

        if not 2 <= len(card.image_query.split()) <= 4:
            raise ValueError(f"{group_id}: image_query는 2~4단어여야 합니다.")

        rules_by_field = option_map[expected_layout].fields

        # 다른 레이아웃에서만 사용하는 필드는 None이어야 함
        for field_name in LAYOUT_FIELDS - set(rules_by_field):
            if getattr(card, field_name) is not None:
                raise ValueError(f"{group_id}: {field_name}은 사용하지 않는 필드입니다.")

        for field_name, rules in rules_by_field.items():
            value = getattr(card, field_name)
            field_type = rules["type"]

            if value is None:
                raise ValueError(f"{group_id}: 필수 필드 {field_name}이 없습니다.")

            if field_type == "text":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{group_id}: {field_name}이 비어 있습니다.")

                maximum = rules["max_chars"]

                if len(value) > maximum:
                    raise ValueError(
                        f"{group_id}: {field_name} 글자 수 초과 "
                        f"(실제 {len(value)}자 / 최대 {maximum}자)"
                    )

                max_newlines = rules.get("max_newlines")

                if max_newlines is not None and value.count("\n") > max_newlines:
                    raise ValueError(f"{group_id}: {field_name} 줄바꿈 수 초과")

            elif field_type == "list":
                minimum = rules["min_items"]
                maximum = rules["max_items"]

                if not minimum <= len(value) <= maximum:
                    raise ValueError(
                        f"{group_id}: {field_name} 항목 수 오류 "
                        f"(실제 {len(value)}개 / 허용 {minimum}~{maximum}개)"
                    )

                for index, item in enumerate(value, start=1):
                    if not item.strip():
                        raise ValueError(
                            f"{group_id}: {field_name} {index}번 항목이 비어 있습니다."
                        )

                    limit = rules["item_max_chars"]

                    if len(item) > limit:
                        raise ValueError(
                            f"{group_id}: {field_name} {index}번 항목 "
                            f"글자 수 초과 (실제 {len(item)}자 / 최대 {limit}자)"
                        )

            elif field_type == "pair":
                if not value.label.strip() or not value.value.strip():
                    raise ValueError(f"{group_id}: {field_name} 비교 내용이 비어 있습니다.")

                label_limit = rules["label_max_chars"]
                value_limit = rules["value_max_chars"]

                if len(value.label) > label_limit:
                    raise ValueError(
                        f"{group_id}: {field_name}.label 글자 수 초과 "
                        f"(실제 {len(value.label)}자 / 최대 {label_limit}자)"
                    )

                if len(value.value) > value_limit:
                    raise ValueError(
                        f"{group_id}: {field_name}.value 글자 수 초과 "
                        f"(실제 {len(value.value)}자 / 최대 {value_limit}자)"
                    )

            else:
                raise ValueError(f"{group_id}: 지원하지 않는 필드 유형 {field_type}")
