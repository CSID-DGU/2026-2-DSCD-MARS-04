import json
import sys
from pathlib import Path
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from experiments.promptfoo.compare.common import summary_items, tag_file

ROOT = Path(__file__).resolve().parents[3]
C_PROMPT = ROOT / "ai/verification/completeness/llm/c_prompt.md"
MODEL = "gpt-6-luna"


class Tag(BaseModel):
    id: str
    priority: Literal["핵심", "부가"]


class Tags(BaseModel):
    tags: list[Tag]


def tag(case_dir: Path, record_file: str, client: OpenAI) -> dict[str, str]:
    """카드를 보기 전에 요약 문장마다 핵심·부가를 정한다. 모든 서비스 판정에 같은 표시를 쓴다."""
    out = case_dir / tag_file(record_file)
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    groups = summary_items(case_dir, record_file, "group")
    sents = summary_items(case_dir, record_file, "sentence")
    core = C_PROMPT.read_text(encoding="utf-8").split("## 4.", 1)[1].split("\n## 5.", 1)[0]
    instructions = (
        "그룹 요약의 각 문장이 그 그룹 안에서 핵심인지 부가인지 정한다. 아래 기준을 따른다.\n"
        "그룹마다 핵심 문장이 최소 하나는 있다. 모든 문장 id에 하나씩 답한다.\n\n" + core
    )
    payload = {
        "groups": [{"group_id": g, "summary": t} for g, t in groups],
        "sentences": [{"id": i, "text": t} for i, t in sents],
    }
    resp = client.responses.parse(
        model=MODEL,
        reasoning={"effort": "none"},
        instructions=instructions,
        input=json.dumps(payload, ensure_ascii=False),
        text_format=Tags,
        temperature=0,
        store=False,
    )
    tags = {t.id: t.priority for t in resp.output_parsed.tags}
    missing = [i for i, _ in sents if i not in tags]
    if missing:
        raise ValueError(f"{case_dir.name} {record_file}: 표시가 빠진 문장 {missing}")
    out.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")
    return tags


if __name__ == "__main__":
    client = OpenAI()
    for arg in sys.argv[1:]:
        case, record_file = arg.split(":")
        tags = tag(ROOT / "data/compare" / case, record_file, client)
        print(case, record_file, len(tags), "핵심", sum(v == "핵심" for v in tags.values()))
