from typing import Any
from pydantic import BaseModel, Field
from data_pipeline.schemas.group import Group


# layouts.json에 정의된 레이아웃 정보
class LayoutOption(BaseModel):
    layout_id: str
    description: str
    fields: dict[str, Any] = Field(default_factory=dict)


# 레이아웃 선택 입력
class LayoutSelectionInput(BaseModel):
    document_id: str
    groups: list[Group]
    available_layouts: list[LayoutOption]


# 그룹별 레이아웃 선택 결과
class LayoutSelection(BaseModel):
    group_id: str
    layout_id: str


# 레이아웃 선택 출력
class LayoutSelectionOutput(BaseModel):
    document_id: str
    layout_selections: list[LayoutSelection]
