# promptfoo 평가 환경 (CardSync)

요약문 비교와 카드뉴스 시각 평가를 같은 방식으로 실행·기록하기 위한 promptfoo 환경이다.

> **현재 상태:** 저장된 fixture로 연결만 확인하는 오프라인 smoke다.
> 실제 CardSync 요약 함수, 직접 GPT 요약, 비전 평가기는 아직 연결하지 않았다.
> 여기서 나오는 PASS/FAIL 비율은 모델 성능이 아니다.

## 실행

```sh
# Node 22.22 이상 필요 (promptfoo 0.125.1 요구 버전)
cd experiments/promptfoo
npm ci
PROMPTFOO_PYTHON=<레포 requirements가 설치된 python> npm run smoke
```

`npm run smoke`는 API 키 환경변수를 지운 뒤 두 설정을 실행하고, 결과를 `expected/`의 기대 판정과 비교한다.
일부 사례는 일부러 실패하게 만들어 두었으므로 promptfoo 화면의 "failed"는 정상이다.
마지막 줄 `문제 0개`와 종료 코드 0이 통과 기준이다.

## 구성

| 파일 | 역할 |
|---|---|
| `summary_smoke.yaml` | 요약 비교 연결 확인. 두 provider(fixture) × 2사례 × 숫자 규칙 2개 |
| `visual_smoke.yaml` | 시각 평가 결과 JSON 형식 검사 연결 확인 |
| `providers/replay.py` | 저장된 출력을 돌려주는 provider. API 호출 없음, 비용 0 |
| `assertions/summary_numbers.py` | `ai/verification/consistency/numbers.py`를 그대로 호출하는 숫자 규칙 |
| `assertions/visual_judgment.py` | 판정 형식(항목 누락·카드 ID·verdict 값·NOT_APPLICABLE 이유) 검사 |
| `fixtures/` | 손으로 만든 연결 확인용 출력 |
| `expected/` | 사례·provider·metric별 기대 PASS/FAIL |
| `scripts/check_results.py` | promptfoo 결과 JSON과 기대 판정 비교 |
| `scripts/run_smoke.sh` | 위 과정을 한 번에 실행 |

결과 파일은 `results/`에 저장되며 git에 올리지 않는다(`.gitignore`의 `experiments/**/results/`).
