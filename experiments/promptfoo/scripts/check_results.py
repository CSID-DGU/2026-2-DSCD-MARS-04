"""promptfoo 결과 JSON을 기대 판정표와 비교한다.

일부 fixture는 일부러 실패하도록 만들어 두었다. 그래서 promptfoo의 '전체 통과'가 아니라
'정해 둔 사례가 정해 둔 대로 통과/실패했는가'를 확인해야 assertion이 실제로 작동하는지 알 수 있다.

실행: python -m experiments.promptfoo.scripts.check_results <results.json> <expected.json>
"""

import json
import sys
from pathlib import Path

Key = tuple[str, str, str]


def _rows(results: dict) -> list[dict]:
    body = results.get("results", results)
    return body.get("results", body) if isinstance(body, dict) else body


def _provider_label(row: dict) -> str:
    provider = row.get("provider") or {}
    return provider.get("label") or provider.get("id") or ""


def compare_results(rows: list[dict], expected: dict[Key, bool]) -> list[str]:
    actual: dict[Key, bool] = {}
    for row in rows:
        case_id = row.get("vars", {}).get("case_id", "")
        provider = _provider_label(row)
        grading = row.get("gradingResult") or {}
        for component in grading.get("componentResults", []):
            metric = (component.get("assertion") or {}).get("metric")
            if metric:
                actual[(case_id, provider, metric)] = bool(component.get("pass"))

    problems = []
    for key, want in expected.items():
        if key not in actual:
            problems.append(f"결과 없음: {key[0]} / {key[1]} / {key[2]}")
        elif actual[key] != want:
            problems.append(
                f"기대와 다름: {key[0]} / {key[1]} / {key[2]} "
                f"기대 {'PASS' if want else 'FAIL'}, 실제 {'PASS' if actual[key] else 'FAIL'}"
            )
    return problems


def load_expected(path: Path) -> dict[Key, bool]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return {(i["case_id"], i["provider"], i["metric"]): bool(i["pass"]) for i in items}


def main(argv: list[str]) -> int:
    results = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    expected = load_expected(Path(argv[2]))
    problems = compare_results(_rows(results), expected)
    for problem in problems:
        print(problem)
    print(f"확인한 기대 판정 {len(expected)}개, 문제 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
