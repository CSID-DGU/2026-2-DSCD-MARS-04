from pydantic import BaseModel

from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import LayoutOption, LayoutSelection


# ① 카드 문구 생성 입력
class CardGenerationInput(BaseModel):
    document_id: str
    groups: list[Group]  # 사용자가 선택한 그룹
    layout_selections: list[LayoutSelection]
    available_layouts: list[LayoutOption]


# ② 그룹별 카드 문구 생성 결과
class CardGeneration(BaseModel):
    group_id: str
    layout_id: str
    title: str
    items: list[str]


# ③ 카드 문구 생성 출력
class CardGenerationOutput(BaseModel):
    document_id: str
    cards: list[CardGeneration]


# ④ 최종 카드 데이터
class Card(BaseModel):
    card_id: str
    group_id: str
    layout_id: str
    title: str
    items: list[str]


class FinalCardOutput(BaseModel):
    document_id: str
    cards: list[Card]