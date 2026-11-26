from data_pipeline.schemas.group import Group


def select_groups(
    groups: list[Group],
    required_group_ids: list[str],
) -> list[Group]:

    group_map = {group.group_id: group for group in groups}

    if len(group_map) != len(groups):
        raise ValueError("중복된 그룹 ID가 있습니다.")

    if len(required_group_ids) != len(set(required_group_ids)):
        raise ValueError("선택된 그룹 ID가 중복되었습니다.")

    if not required_group_ids:
        raise ValueError("선택된 그룹이 없습니다.")

    invalid_ids = [group_id for group_id in required_group_ids if group_id not in group_map]

    if invalid_ids:
        raise ValueError(f"존재하지 않는 그룹 ID: {invalid_ids}")

    return [group_map[group_id] for group_id in required_group_ids]
