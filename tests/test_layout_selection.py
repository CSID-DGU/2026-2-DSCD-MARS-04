from ai.generation.layout_selector import select_layouts
from data_pipeline.schemas.group import Group

groups = [
    Group(
        group_id="G1",
        sentence_ids=["S1"],
        summary="청년 주거 지원 사업은 올해 11월부터 시행된다.",
        topic="청년 주거 지원",
        headline="11월부터 지원 사업 시행",
    ),
    Group(
        group_id="G2",
        sentence_ids=["S2"],
        summary=("지원 대상은 만 19세 이상 34세 이하이며, 소득 기준을 충족해야 한다."),
        topic="지원 대상",
        headline="나이와 소득 기준 충족 필요",
    ),
    Group(
        group_id="G3",
        sentence_ids=["S3"],
        summary="지원 금액은 기존 월 10만 원에서 월 20만 원으로 인상된다.",
        topic="지원 금액 변경",
        headline="월 지원금 10만 원에서 20만 원으로 인상",
    ),
    Group(
        group_id="G4",
        sentence_ids=["S4"],
        summary="신청자는 온라인 접수 후 서류 심사를 거쳐 최종 결과를 통보받는다.",
        topic="신청 절차",
        headline="온라인 접수부터 결과 통보까지",
    ),
]


def main():
    result = select_layouts(
        document_id="news_001",
        groups=groups,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
