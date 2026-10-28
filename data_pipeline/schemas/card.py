from typing import Literal

from pydantic import BaseModel, model_validator

from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import LayoutOption, LayoutSelection


# ① 카드 문구 생성 입력
class CardGenerationInput(BaseModel):
    document_id: str
    groups: list[Group]
    layout_selections: list[LayoutSelection]
    available_layouts: list[LayoutOption]


# ② 비교형 카드의 왼쪽·오른쪽 내용
class CompareSide(BaseModel):
    label: str
    value: str


# ③ 레이아웃별 카드 문구 생성 결과
class CardGeneration(BaseModel):
    group_id: str | None
    layout_id: Literal["cover", "body", "compare", "checklist", "steps", "closing"]
    sids: list[str]
    title: str
    image_query: str

    # 레이아웃별 필드
    category: str | None = None
    body: str | None = None
    items: list[str] | None = None
    left: CompareSide | None = None
    right: CompareSide | None = None
    cta: str | None = None

    @model_validator(mode="after")
    def validate_layout_fields(self):
        """레이아웃에 필요한 필드와 그룹 연결 관계를 검증한다."""

        required_fields = {
            "cover": ["category"],
            "body": ["body"],
            "compare": ["left", "right"],
            "checklist": ["items"],
            "steps": ["items"],
            "closing": ["body", "cta"],
        }

        if not self.title.strip():
            raise ValueError("카드 제목은 비어 있을 수 없습니다.")

        if not self.image_query.strip():
            raise ValueError("이미지 검색어는 비어 있을 수 없습니다.")

        for field_name in required_fields[self.layout_id]:
            value = getattr(self, field_name)

            if value is None or value == "" or value == []:
                raise ValueError(f"{self.layout_id} 레이아웃에 {field_name} 필드가 필요합니다.")

        if self.layout_id in ("cover", "closing"):
            if self.group_id is not None:
                raise ValueError("표지와 마무리 카드는 group_id가 None이어야 합니다.")
        else:
            if not self.group_id:
                raise ValueError("본문 그룹 카드에는 group_id가 필요합니다.")

            if not self.sids:
                raise ValueError("본문 그룹 카드에는 근거 문장 ID가 필요합니다.")

        if self.layout_id in ("checklist", "steps"):
            if len(self.items) < 2 or len(self.items) > 6:
                raise ValueError("체크리스트와 단계형 카드는 항목이 2~6개여야 합니다.")

        return self


# ④ 카드 문구 생성 출력
class CardGenerationOutput(BaseModel):
    document_id: str
    cards: list[CardGeneration]


# ⑤ 최종 카드 데이터
class Card(CardGeneration):
    card_id: str


class FinalCardOutput(BaseModel):
    document_id: str
    cards: list[Card]
