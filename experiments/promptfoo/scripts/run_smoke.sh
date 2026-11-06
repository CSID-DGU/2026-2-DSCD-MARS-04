#!/bin/sh
# 오프라인 smoke 평가: 실제 promptfoo eval을 돌리고, 결과를 기대 판정표와 비교한다.
# API 키를 지우고 실행하므로 유료 모델이 호출되지 않는다.
#
# promptfoo는 실패한 테스트가 하나라도 있으면 종료 코드 100을 낸다.
# 이 smoke에는 일부러 실패하도록 만든 사례가 있으므로 100은 정상이고,
# 실제 통과 기준은 check_results.py의 기대 판정 비교다.
set -u

HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
OUT="$HERE/results"
PYTHON_BIN="${PROMPTFOO_PYTHON:-python3}"
mkdir -p "$OUT"

export PROMPTFOO_PYTHON="$PYTHON_BIN"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PROMPTFOO_DISABLE_TELEMETRY=1
export PROMPTFOO_DISABLE_UPDATE=1
export PROMPTFOO_DISABLE_REMOTE_GENERATION=true
unset OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY

status=0
for name in summary_smoke visual_smoke compare_smoke; do
  echo "== $name =="
  (cd "$HERE" && npx promptfoo eval -c "$name.yaml" --no-cache --no-share -o "$OUT/$name.json")
  code=$?
  if [ "$code" -ne 0 ] && [ "$code" -ne 100 ]; then
    echo "promptfoo 실행 오류 (종료 코드 $code)"
    status=1
    continue
  fi
  (cd "$ROOT" && "$PYTHON_BIN" -m experiments.promptfoo.scripts.check_results \
    "$OUT/$name.json" "$HERE/expected/$name.json") || status=1
done

exit $status
