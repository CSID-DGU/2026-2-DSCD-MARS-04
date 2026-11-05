"""레포 AI 함수 연결부.

서비스 계층은 이 Protocol만 안다. 기본 구현(RepoPipeline)은 팀원 함수를 import해서
그대로 부르고, 테스트는 같은 모양의 가짜 구현을 주입한다. 팀원 코드는 고치지 않는다.
"""

from __future__ import annotations

from typing import Any, Protocol

CHECKER_NAME = "summary-consistency@8c9242c"
CARD_CHECKER_NAME = "card-factuality-llm+completeness+feedback"


class Pipeline(Protocol):
    def split(self, text: str) -> list[dict]: ...

    def analyze(self, document_id: str, text: str) -> list[dict]: ...

    def titles(self, document_id: str, groups: list[dict]) -> list[dict]: ...

    def generate(self, document_id: str, groups: list[dict]) -> list[dict]: ...

    def check(self, items: list[dict]) -> list[dict]:
        """요약 단계: 원문 문장 ↔ 그룹 요약 (서준 consistency 검사기)."""
        ...

    def check_cards(self, document_id: str, groups: list[dict], cards: list[dict]) -> dict:
        """카드 단계: 그룹 요약 ↔ 카드 문구 (수연 사실성 + 완전성 + 피드백 통합).

        반환: {"status", "model", "cards": {card_id: {...}}, "feedback": [...], "unchecked": [...]}
        """
        ...


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

    def photo(self, query: str, exclude: set[str]) -> dict | None:
        from backend.services.unsplash import search_photo

        return search_photo(query, exclude=exclude)

    def check(self, items: list[dict]) -> list[dict]:
        from ai.verification.consistency.checker import check_consistency

        return check_consistency(items, by_sentence=True, client=self.client)["results"]

    def check_cards(self, document_id: str, groups: list[dict], cards: list[dict]) -> dict:
        from dataclasses import asdict

        from ai.verification.completeness.llm.llm_checker import check_llm_completeness
        from ai.verification.factuality.llm.llm_checker import check_llm_factuality
        from ai.verification.feedback.merger import merge_feedback
        from data_pipeline.schemas.card import Card, FinalCardOutput
        from data_pipeline.schemas.group import Group

        models = [Group.model_validate(g) for g in groups]
        final = FinalCardOutput(
            document_id=document_id, cards=[Card.model_validate(c) for c in cards]
        )
        factuality = check_llm_factuality(models, final, client=self.client)
        completeness = check_llm_completeness(models, final, client=self.client)
        feedback = merge_feedback(factuality, completeness, client=self.client)
        return {
            "status": feedback.status,
            "model": factuality.model,
            "cards": {
                c.card_id: {"status": c.status, "fields": [asdict(f) for f in c.fields]}
                for c in factuality.cards
            },
            "completeness": [r.model_dump() for r in completeness.results],
            "feedback": [i.model_dump() for i in feedback.items],
            "unchecked": list(feedback.unchecked),
            "input_tokens": factuality.input_tokens
            + completeness.input_tokens
            + feedback.input_tokens,
            "output_tokens": factuality.output_tokens
            + completeness.output_tokens
            + feedback.output_tokens,
        }
