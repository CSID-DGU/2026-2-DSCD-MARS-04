"""저장된 출력을 그대로 돌려주는 오프라인 provider (API 호출 없음).

promptfoo Python provider 규약: call_api(prompt, options, context).
options["config"]["fixture"]: fixtures/ 아래 JSON 파일 이름
options["config"]["system"]: 그 파일 안의 시스템 이름
context["vars"]["case_id"]: 돌려줄 사례 ID

나중에 실제 생성·평가 함수를 연결하기 전까지 파이프라인 연결만 확인하는 용도다.
여기서 나온 점수는 모델 성능이 아니다.
"""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def call_api(prompt: str, options: dict, context: dict) -> dict:
    config = options.get("config", {})
    fixture_name = config["fixture"]
    system = config["system"]
    case_id = context["vars"]["case_id"]

    data = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    output = data.get(system, {}).get(case_id)

    if output is None:
        return {"error": f"{fixture_name}에 {system}/{case_id} 저장 출력이 없습니다."}

    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False)

    return {
        "output": output,
        "tokenUsage": {"total": 0, "prompt": 0, "completion": 0},
        "cost": 0,
        "metadata": {"fixture": True, "system": system, "case_id": case_id},
    }
