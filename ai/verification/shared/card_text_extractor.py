from dataclasses import dataclass

from data_pipeline.schemas.card import Card, FinalCardOutput

GROUP_LAYOUTS = {"body", "compare", "checklist", "steps"}


@dataclass(frozen=True)
class CardTextUnit:
    unit_id: str
    card_id: str
    group_id: str
    layout_id: str
    field_path: str
    text: str
    context: str
    sids: tuple[str, ...]


def add_unit(
    units: list[CardTextUnit],
    card: Card,
    field_path: str,
    text: str,
    context: str | None = None,
) -> None:
    text = text.strip()
    if not text:
        return

    units.append(
        CardTextUnit(
            unit_id=f"{card.card_id}:{field_path}",
            card_id=card.card_id,
            group_id=card.group_id,
            layout_id=card.layout_id,
            field_path=field_path,
            text=text,
            context=context.strip() if context else text,
            sids=tuple(card.sids),
        )
    )


def extract_card_text(card: Card) -> list[CardTextUnit]:
    """Extract verifiable text from one group-linked card."""

    if card.layout_id not in GROUP_LAYOUTS:
        return []

    units: list[CardTextUnit] = []
    title = card.title.strip()

    add_unit(units, card, "title", title)

    if card.layout_id == "body":
        if card.body:
            add_unit(
                units,
                card,
                "body",
                card.body,
                context=f"{title}\n{card.body}",
            )

    elif card.layout_id == "compare":
        for side_name in ("left", "right"):
            side = getattr(card, side_name)

            if side is None:
                continue

            combined = " — ".join(part for part in (side.label.strip(), side.value.strip()) if part)

            add_unit(
                units,
                card,
                side_name,
                combined,
                context=f"{title}\n{combined}",
            )

    elif card.layout_id in ("checklist", "steps"):
        for index, item in enumerate(card.items or []):
            add_unit(
                units,
                card,
                f"items[{index}]",
                item,
                context=f"{title}\n{item}",
            )

    return units


def extract_card_texts(
    final_cards: FinalCardOutput,
) -> list[CardTextUnit]:
    """Extract all verifiable card text."""

    units: list[CardTextUnit] = []

    for card in final_cards.cards:
        units.extend(extract_card_text(card))

    return units


def group_text_units(
    units: list[CardTextUnit],
) -> dict[str, list[CardTextUnit]]:
    """Group extracted units by group_id."""

    grouped: dict[str, list[CardTextUnit]] = {}

    for unit in units:
        grouped.setdefault(unit.group_id, []).append(unit)

    return grouped
