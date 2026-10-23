from pydantic import BaseModel

from data_pipeline.schemas.group import Group


# layouts.json에 정의된 레이아웃 정보
class LayoutOption(BaseModel):
    layout_id: str
    description: str
    # 추후 결과값에 반영할 수 있도록 레이아웃별 제약 조건을 정의할 수 있음
    # max_items: int | None = None
    # max_chars_per_item: int | None = None


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