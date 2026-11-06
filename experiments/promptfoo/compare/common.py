"""완성 카드 비교 판정의 공통 정의.

판정 질문은 compare/questions.json 하나에서 읽는다. provider·assertion·내보내기 스크립트가
같은 정의를 쓰게 해서 질문 목록이 서로 어긋나지 않게 한다.

비교 사례 폴더 구조 (data/compare/ 아래, git에 올리지 않음):
    <기사 ID>/source.txt           원문 전체
    <기사 ID>/facts.json           필수 정보. 생성 전에 확정. 목록 [{"id": "F1", "text": "..."}]
                                   또는 {"facts": [...], "excluded": [...]} 객체. 항목에
                                   표현 강도 wording(미확정·요청)과 원문 표현 hedge가 붙을 수 있다
    <기사 ID>/<서비스>/*.png       카드 이미지. 파일 이름 순서가 카드 순서(C1, C2, ...)
    <기사 ID>/<서비스>/human.json  (선택) 사람 판정. provider 출력과 같은 형식
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions.json"

# AI에게 묻지 않는 판정자: 렌더 기록 자동 판정(D-07), 렌더 측정값(D-06)
NOT_ASKED_JUDGES = {"auto"}


def load_questions(path: Path = QUESTIONS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


FACT_FIELDS = ("id", "text", "wording", "hedge")


def load_facts(path: Path) -> list[dict]:
    """판정 모델에 넘길 필수 정보 목록.

    facts.json은 목록 그대로이거나, facts·excluded·확정 기록을 담은 객체다. 판정에는
    필수 정보의 ID·문장·표현 강도만 넘긴다. 제외 목록을 넘기면 모델이 그것까지 판정할 수 있다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = data["facts"] if isinstance(data, dict) else data
    return [{k: f[k] for k in FACT_FIELDS if f.get(k)} for f in facts]


def ai_questions(spec: dict | None = None) -> list[dict]:
    """AI 판정 대상 질문 (측정값·자동 판정 제외)."""
    spec = spec or load_questions()
    return [q for q in spec["questions"] if q["judge"] not in NOT_ASKED_JUDGES]


def allowed_verdicts(question: dict, spec: dict | None = None) -> list[str]:
    spec = spec or load_questions()
    return spec["verdicts"][question["kind"]]


def card_ids_for(images: list[Path]) -> list[str]:
    return [f"C{i}" for i in range(1, len(images) + 1)]


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})


def expected_keys(card_ids: list[str], fact_ids: list[str], spec: dict | None = None) -> set:
    """판정이 반드시 있어야 하는 (질문, 카드, 필수 정보) 조합."""
    keys = set()
    for q in ai_questions(spec):
        if q["scope"] == "card":
            keys |= {(q["id"], cid, None) for cid in card_ids}
        elif q["scope"] == "set":
            keys.add((q["id"], None, None))
        elif q["scope"] == "fact":
            keys |= {(q["id"], None, fid) for fid in fact_ids}
    return keys


def judgment_key(item: dict) -> tuple:
    return (item.get("question_id"), item.get("card_id") or None, item.get("fact_id") or None)


_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """인용 확인용: 공백 차이만 무시한다."""
    return _SPACE.sub(" ", str(text)).strip()
