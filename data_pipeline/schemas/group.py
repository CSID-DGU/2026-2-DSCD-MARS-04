from pydantic import BaseModel


# ① 분석 Agent
class Sentence(BaseModel):
    sentence_id: str
    text: str


class GroupAnalysis(BaseModel):
    group_id: str
    sentence_ids: list[str]
    summary: str


class GroupAnalysisInput(BaseModel):
    document_id: str
    sentences: list[Sentence]


class GroupAnalysisOutput(BaseModel):
    document_id: str
    groups: list[GroupAnalysis]


# ② 그룹 제목 생성
class GroupPresentation(BaseModel):
    group_id: str
    topic: str
    headline: str


class GroupPresentationInput(BaseModel):
    document_id: str
    groups: list[GroupAnalysis]


class GroupPresentationOutput(BaseModel):
    document_id: str
    group_presentations: list[GroupPresentation]


# ③ 분석 결과 + 그룹 제목 통합
class Group(BaseModel):
    group_id: str
    sentence_ids: list[str]
    summary: str
    topic: str
    headline: str


# ④ 사용자 필수 그룹 선택
class GroupSelectionOutput(BaseModel):
    document_id: str
    required_group_ids: list[str]