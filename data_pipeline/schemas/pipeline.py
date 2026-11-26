from typing import Literal

from pydantic import BaseModel

from data_pipeline.schemas.card import Card


# 생성 → 완전성 검사 → 오류 수정·재검사 최종 결과
class GenerationPipelineResult(BaseModel):
    document_id: str
    status: Literal["PASS", "FAIL"]
    correction_count: int
    cards: list[Card]
