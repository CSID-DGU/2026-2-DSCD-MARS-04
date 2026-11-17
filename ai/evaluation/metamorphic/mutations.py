from copy import deepcopy

CASES = [
    {
        "id": "F01",
        "type": "factuality",
        "name": "지원 대수 변경",
        "group_id": "G1",
        "target": "items[0]",
        "old": "196대",
        "new": "296대",
        "expected": ["POSSIBLE_DISTORTION"],
    },
    {
        "id": "F02",
        "type": "factuality",
        "name": "가능성을 확정으로 변경",
        "group_id": "G2",
        "target": "body",
        "old": "탈락할 가능성이 있으니",
        "new": "반드시 탈락하니",
        "expected": ["POSSIBLE_DISTORTION"],
    },
    {
        "id": "F03",
        "type": "factuality",
        "name": "출고 기한 변경",
        "group_id": "G3",
        "target": "items[3]",
        "old": "2개월",
        "new": "3개월",
        "expected": ["POSSIBLE_DISTORTION"],
    },
    {
        "id": "F04",
        "type": "factuality",
        "name": "의미 보존 의역",
        "group_id": "G2",
        "target": "body",
        "old": (
            "장애인 등 사회취약계층은 전기차 구매 후 차량가액에 따라 "
            "기초연금, 장애인연금 수급에서 탈락할 가능성이 있으니 "
            "주의해야 합니다."
        ),
        "new": (
            "전기차를 구매하는 사회취약계층은 차량가액에 따라 "
            "기초연금이나 장애인연금 수급 대상에서 제외될 수 "
            "있으므로 주의가 필요합니다."
        ),
        "expected": ["SUPPORTED"],
    },
    {
        "id": "C01",
        "type": "completeness",
        "name": "출고 조건 삭제",
        "group_id": "G3",
        "target": "items[3]",
        "old": "2개월 내 출고 없으면 선정 취소·대기자 전환",
        "new": None,
        "expected": ["PARTIALLY_COVERED"],
    },
    {
        "id": "C02",
        "type": "completeness",
        "name": "그룹 전체 누락",
        "group_id": "G2",
        "target": "card",
        "old": None,
        "new": None,
        "expected": ["MISSING"],
    },
]


def find_card(cards, group_id):
    matches = [card for card in cards if card.get("group_id") == group_id]

    if len(matches) != 1:
        raise ValueError(f"{group_id} 카드가 정확히 1장이어야 합니다. 현재 {len(matches)}장")

    return matches[0]


def read_field(card, field_path):
    if field_path.startswith("items[") and field_path.endswith("]"):
        index = int(field_path[6:-1])
        return card["items"][index]

    return card[field_path]


def write_field(card, field_path, value):
    if field_path.startswith("items[") and field_path.endswith("]"):
        index = int(field_path[6:-1])

        if value is None:
            card["items"].pop(index)
        else:
            card["items"][index] = value

        return

    card[field_path] = value


def mutate_cards(original, case):
    mutated = deepcopy(original)
    cards = mutated["cards"]

    if case["target"] == "card":
        matches = [card for card in cards if card.get("group_id") == case["group_id"]]

        if not matches:
            raise ValueError("삭제할 그룹 카드가 없습니다.")

        mutated["cards"] = [card for card in cards if card.get("group_id") != case["group_id"]]

        return mutated, {
            "before": matches,
            "after": None,
        }

    card = find_card(cards, case["group_id"])
    before = read_field(card, case["target"])

    if case["new"] is None:
        if before != case["old"]:
            raise ValueError(f"삭제 대상이 예상과 다릅니다: {before}")

        write_field(card, case["target"], None)

        after = None

    elif case["target"] == "body" and case["id"] == "F04":
        if before != case["old"]:
            raise ValueError("의역 대상 원문이 예상과 다릅니다.")

        after = case["new"]
        write_field(card, case["target"], after)

    else:
        old = case["old"]
        new = case["new"]

        if before.count(old) != 1:
            raise ValueError(f"치환 대상이 정확히 1개가 아닙니다: {old}")

        after = before.replace(old, new, 1)
        write_field(card, case["target"], after)

    return mutated, {
        "before": before,
        "after": after,
    }
