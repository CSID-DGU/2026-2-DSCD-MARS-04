"""실제 판결 기사 요약문으로 레이아웃 선택 및 카드 문구 생성 테스트."""

from ai.generation.card_generator import generate_cards
from ai.generation.layout_selector import select_layouts
from data_pipeline.schemas.group import Group


def main():
    data = [
        (
            "G1",
            ["S1", "S2"],
            (
                "대법원 제1부는 도주치상 혐의로 재판에 넘겨진 김씨에 대해 "
                "유죄 원심 판결을 무죄 취지로 파기하고 사건을 춘천지법 "
                "강릉지원 합의부에 돌려보냈다. 대법원은 피고인이 피해자로부터 "
                "괜찮다는 말을 듣고 비교적 경미한 사고라고 판단해 사고장소를 "
                "이탈했을 가능성이 있다며 도주의 범의로 사고현장을 이탈해 "
                "사고를 낸 자가 누구인지 확정할 수 없는 상태를 초래한 것으로 "
                "단정하기 어렵다고 판단했다."
            ),
            "대법원 판결",
            "도주치상 사건, 무죄 취지 파기환송",
        ),
        (
            "G2",
            ["S3", "S4", "S5", "S6", "S7"],
            (
                "김씨는 2016년 10월 오후 4시쯤 택시를 운전해 삼척시 한 읍내 "
                "도로를 달리다 우측 사이드미러로 피해자 이씨 왼팔을 들이받았다. "
                "김씨는 즉시 차를 세워 조수석 창문을 열어 피해자와 몇 마디 "
                "대화를 한 후 원래 진행방향으로 택시를 운전해 갔다. "
                "사고 후 피해자는 곧바로 병원에 가지 않고 원래 일정에 따라 "
                "주위에서 장을 본 후 집으로 돌아갔다. 이씨는 이후 이 사고로 "
                "3주간 치료가 필요한 상해 진단을 받았다. "
                "두 사람은 서로 일면식이 있어 상대가 누군지 알았다."
            ),
            "사고 경위",
            "택시 사이드미러 접촉사고와 이후 상황",
        ),
        (
            "G3",
            ["S8", "S9", "S10"],
            (
                "재판 쟁점은 사고 직후 택시 운전사가 피해자에게 어떤 대화를 "
                "했는지였다. 택시 기사는 피해자에게 괜찮냐고 물었는데 "
                "피해자가 괜찮다고 해 그냥 간 것이라고 진술했다. "
                "반면 피해자는 당시 괜찮다는 말을 한 적이 없다고 맞섰다."
            ),
            "당사자 진술",
            "사고 직후 대화를 둘러싼 엇갈린 주장",
        ),
        (
            "G4",
            ["S11", "S12", "S13"],
            (
                "1심은 피해자 진술에 신빙성이 없다며 공소를 기각했다. "
                "증인신문 절차에서 증인 모습과 태도를 관찰한 결과 "
                "증인 진술에 신빙성을 인정할 수 없다고 봤다. "
                "법원은 피해자가 과장하거나 유리하게 진술했을 가능성과 "
                "치료를 과하게 받았을 가능성을 배제할 수 없으며 "
                "일면식 있는 상황에서 피고인이 도주한다는 것은 "
                "생각하기 어렵다고 봤다."
            ),
            "1심 판단",
            "피해자 진술의 신빙성을 인정하기 어렵다고 판단",
        ),
        (
            "G5",
            ["S14", "S15", "S16"],
            (
                "2심은 피해자가 사고 당시 상황에 대해 수사기관 진술을 "
                "대체로 유지한다며 피해자 진술 신빙성을 인정해 1심을 파기했다. "
                "다만 죄가 있으나 사안이 경미해 김씨에게 형 선고를 유예했다."
            ),
            "2심 판단",
            "피해자 진술 신빙성 인정, 형 선고 유예",
        ),
        (
            "G6",
            ["S17", "S18"],
            (
                "대법원은 1심 판단이 옳다고 봤다. "
                "재판부는 항소심이 1심 판단과 달리 진술 신빙성을 인정하려면 "
                "1심 판단을 수긍할 수 없는 충분하고 납득할 만한 현저한 "
                "사정이 나타나야 한다며 원심을 파기했다."
            ),
            "대법원 판단 근거",
            "1심의 신빙성 판단을 뒤집기 위한 요건 제시",
        ),
    ]

    groups = [
        Group(
            group_id=group_id,
            sentence_ids=sentence_ids,
            summary=summary,
            topic=topic,
            headline=headline,
        )
        for group_id, sentence_ids, summary, topic, headline in data
    ]

    document_id = "court_article_001"

    layout_result = select_layouts(
        document_id=document_id,
        groups=groups,
    )

    print("=== 레이아웃 선택 결과 ===")
    print(layout_result.model_dump_json(indent=2))

    card_result = generate_cards(
        document_id=document_id,
        groups=groups,
        layout_selections=layout_result.layout_selections,
    )

    print("=== 카드 문구 생성 결과 ===")
    print(card_result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
