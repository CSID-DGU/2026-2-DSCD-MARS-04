"""레포 AI 함수 연결부.

서비스 계층은 이 Protocol만 안다. 기본 구현(RepoPipeline)은 팀원 함수를 import해서
그대로 부르고, 테스트는 같은 모양의 가짜 구현을 주입한다. 팀원 코드는 고치지 않는다.
"""

from __future__ import annotations

from typing import Any, Protocol

CHECKER_NAME = "summary-consistency@8c9242c"


class Pipeline(Protocol):
    def split(self, text: str) -> list[dict]: ...

    def analyze(self, document_id: str, text: str) -> list[dict]: ...

    def titles(self, document_id: str, groups: list[dict]) -> list[dict]: ...

    def generate(self, document_id: str, groups: list[dict]) -> list[dict]: ...

    def check(self, items: list[dict]) -> list[dict]: ...


class RepoPipeline:
    """팀 레포 dev의 함수를 순서대로 호출한다. LLM 호출이 있어 OPENAI_API_KEY가 필요하다."""

    def __init__(self, client: Any | None = None):
        self.client = client

    def split(self, text: str) -> list[dict]:
        from data_pipeline.extraction.llm.sentence_splitter import split_sentences

        return split_sentences(text)

    def analyze(self, document_id: str, text: str) -> list[dict]:
        from ai.analysis.agent import analyze

        return analyze(document_id, text, client=self.client)["groups"]

    def titles(self, document_id: str, groups: list[dict]) -> list[dict]:
        from ai.generation.group_merger import merge_group_results
        from ai.generation.group_titles import generate_group_titles
        from data_pipeline.schemas.group import GroupAnalysisOutput, GroupPresentationOutput

        titles = generate_group_titles(
            {"document_id": document_id, "groups": groups}, client=self.client
        )
        # 두 모델의 필드는 같지만 클래스가 달라 dict를 거쳐 맞춘다
        presentation = GroupPresentationOutput.model_validate(titles.model_dump())
        analysis = GroupAnalysisOutput.model_validate(
            {"document_id": document_id, "groups": groups}
        )
        return [g.model_dump() for g in merge_group_results(analysis, presentation)]

    def generate(self, document_id: str, groups: list[dict]) -> list[dict]:
        from ai.generation.card_generator import generate_cards
        from ai.generation.layout_selector import select_layouts
        from data_pipeline.schemas.group import Group

        models = [Group.model_validate(g) for g in groups]
        layouts = select_layouts(document_id, models, client=self.client)
        result = generate_cards(document_id, models, layouts.layout_selections, client=self.client)
        return [c.model_dump() for c in result.cards]

    def check(self, items: list[dict]) -> list[dict]:
        from ai.verification.consistency.checker import check_consistency

        return check_consistency(items, by_sentence=True, client=self.client)["results"]
