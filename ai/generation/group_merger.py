from data_pipeline.schemas.group import (
    Group,
    GroupAnalysisOutput,
    GroupPresentationOutput,
)


def merge_group_results(
    analysis: GroupAnalysisOutput,
    presentation: GroupPresentationOutput,
) -> list[Group]:
    # 동일한 문서인지 확인
    if analysis.document_id != presentation.document_id:
        raise ValueError("document_id가 일치하지 않습니다.")

    # 제목 생성 결과를 group_id 기준으로 저장
    title_map = {}

    for item in presentation.group_presentations:
        if item.group_id in title_map:
            raise ValueError(f"중복된 group_id: {item.group_id}")

        title_map[item.group_id] = item

    # 분석 결과의 group_id 확인
    analysis_ids = [group.group_id for group in analysis.groups]

    if len(analysis_ids) != len(set(analysis_ids)):
        raise ValueError("분석 결과에 중복된 group_id가 있습니다.")

    # 그룹 누락 또는 추가 여부 확인
    if set(analysis_ids) != set(title_map):
        raise ValueError("분석 결과와 제목 생성 결과의 group_id가 일치하지 않습니다.")

    # 기존 분석 그룹 순서를 유지하면서 통합
    merged_groups = []

    for group in analysis.groups:
        title = title_map[group.group_id]

        merged_groups.append(
            Group(
                group_id=group.group_id,
                sentence_ids=group.sentence_ids,
                summary=group.summary,
                topic=title.topic,
                headline=title.headline,
            )
        )

    return merged_groups
