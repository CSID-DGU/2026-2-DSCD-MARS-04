from pydantic import BaseModel


# 분석 Agent 출력
class GroupAnalysis(BaseModel):
    group_id: str
    sentence_ids: list[str]
    summary: str


# 생성 Agent 출력
class GroupPresentation(BaseModel):
    group_id: str
    topic: str
    headline: str


# 최종 통합 결과
class Group(BaseModel):
    group_id: str
    sentence_ids: list[str]
    summary: str
    topic: str
    headline: str
