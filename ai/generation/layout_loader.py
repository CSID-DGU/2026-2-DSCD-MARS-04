import json
from pathlib import Path

from data_pipeline.schemas.layout import LayoutOption


def load_layout_options(json_path: str | Path) -> list[LayoutOption]:

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


def load_all_layout_options(json_path: str | Path) -> list[LayoutOption]:

    with Path(json_path).open(encoding="utf-8") as file:
        layouts = json.load(file)["layouts"]

    return [
        LayoutOption(
            layout_id=layout_id,
            description=definition["when"],
            fields=definition["fields"],
        )
        for layout_id, definition in layouts.items()
    ]
