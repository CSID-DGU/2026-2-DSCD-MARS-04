import json
from pathlib import Path

from data_pipeline.schemas.layout import LayoutOption


def load_layout_options(json_path: str | Path) -> list[LayoutOption]:
    """layouts.json에서 그룹별 선택 가능한 레이아웃을 불러온다."""

    with Path(json_path).open(encoding="utf-8") as file:
        data = json.load(file)

    layouts = data["layouts"]
    group_layout_ids = data["group_layouts"]

    return [
        LayoutOption(
            layout_id=layout_id,
            description=layouts[layout_id]["when"],
            fields=layouts[layout_id]["fields"],
        )
        for layout_id in group_layout_ids
    ]
