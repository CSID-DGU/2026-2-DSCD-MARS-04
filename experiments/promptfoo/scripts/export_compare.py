"""promptfoo 비교 판정 결과를 평가표 '판정기록' 시트 형식 CSV로 내보낸다.

사실성·완전성은 따로 요약한다.

실행: python -m experiments.promptfoo.scripts.export_compare <results.json> <out.csv>

- 판정자 열은 "AI"로 적는다. C-01·C-02는 AI 후보이며, 사람 판정은 평가표에서 따로 입력한다.
- 사실성(C-01)과 완전성(C-02)은 합산하지 않는다.
  하나의 오류가 C-01 미충족과 C-02 왜곡에 같이 잡힐 수 있다.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from experiments.promptfoo.compare.common import load_questions

HEADER = [
    "기사 No",
    "서비스",
    "판정자",
    "질문 ID",
    "카드 번호",
    "판정",
    "측정값",
    "근거(보이는 문구·위치)",
    "판정 방법",
    "판정 날짜",
    "필수 정보 ID(C-02만)",
]


def _rows(results: dict) -> list[dict]:
    body = results.get("results", results)
    return body.get("results", body) if isinstance(body, dict) else body


def _method(qid: str, service: str, spec: dict) -> str:
    q = next(q for q in spec["questions"] if q["id"] == qid)
    if q["judge"] == "ai_candidate":
        return "AI 후보(PNG+원문) — 사람 확정 필요"
    if q["judge"] == "ai_png" and service == "CardSync":
        return "AI(PNG) 참고 — 최종은 렌더 화면 자동 측정"
    return "AI(PNG)"


def to_records(results: dict, date: str = "") -> list[list]:
    spec = load_questions()
    labels = spec["verdict_labels"]
    records = []
    for row in _rows(results):
        vars_ = row.get("vars", {})
        service = vars_.get("service", "")
        try:
            judgments = json.loads((row.get("response") or {}).get("output") or "")["judgments"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        for j in judgments:
            qid = j.get("question_id", "")
            spans = j.get("spans") or []
            evidence = str(j.get("evidence") or j.get("reason") or "")
            if spans:
                evidence += " | " + " / ".join(
                    f"{s.get('card_id', '')}: {s.get('card_text', '')}"
                    f" ← 원문: {s.get('source_quote', '')}"
                    for s in spans
                )
            measure = len(spans) if qid == "C-01" and j.get("verdict") == "NOT_MET" else ""
            records.append(
                [
                    vars_.get("article_no", vars_.get("case_id", "")),
                    service,
                    "AI",
                    qid,
                    j.get("card_id") or "",
                    labels.get(j.get("verdict"), j.get("verdict")),
                    measure,
                    evidence.strip(" |"),
                    _method(qid, service, spec),
                    date,
                    j.get("fact_id") or "",
                ]
            )
    return records


def summarize(records: list[list]) -> dict[str, dict]:
    """서비스별 사실성·완전성 요약 (AI 후보 기준)."""
    out: dict[str, dict] = {}
    for svc in sorted({r[1] for r in records}):
        rows = [r for r in records if r[1] == svc]
        fact = [r for r in rows if r[3] == "C-01"]
        judged = [r for r in fact if r[5] in ("충족", "미충족")]
        bad = [r for r in judged if r[5] == "미충족"]
        comp = Counter(r[5] for r in rows if r[3] == "C-02")
        n = comp["전달"] + comp["누락"] + comp["왜곡"]
        out[svc] = {
            "사실성_틀린문구수": sum(int(r[6] or 0) for r in fact),
            "사실성_오류카드비율": round(len(bad) / len(judged), 3) if judged else None,
            "완전성_전달": comp["전달"],
            "완전성_누락": comp["누락"],
            "완전성_왜곡": comp["왜곡"],
            "완전성_판단보류": comp["판단 보류"],
            "완전성_전달률": round(comp["전달"] / n, 3) if n else None,
        }
    return out


def main(argv: list[str]) -> int:
    results = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    records = to_records(results)
    with open(argv[2], "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(records)
    print(f"판정 {len(records)}행 → {argv[2]}")
    print("사실성·완전성 요약 (AI 후보 기준, 합산하지 않음):")
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
