from typing import Literal

from pydantic import BaseModel

from data_pipeline.schemas.card import Card
from data_pipeline.schemas.group import Group, Sentence


# ① 완전성 검사 입력
class CompletenessInput(BaseModel):
    document_id: str
    required_group_ids: list[str]
    groups: list[Group]
    sentences: list[Sentence]
    cards: list[Card]


# ② 필수 그룹별 검사 결과
class GroupCompletenessResult(BaseModel):
    group_id: str
    status: Literal["PASS", "FAIL"]
    related_card_ids: list[str]
    missing_information: list[str]


# ③ 완전성 검사 출력
class CompletenessOutput(BaseModel):
    document_id: str
    completeness_status: Literal["PASS", "FAIL"]
    group_results: list[GroupCompletenessResult]
