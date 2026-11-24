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

## 완성 카드 비교 (CardSync vs 망고보드)

같은 기사로 두 서비스가 만든 최종 카드 PNG를 같은 판정 질문으로 판정한다. 판정 질문은 `compare/questions.json` 하나에서 읽고, 팀 평가표 '판정질문' 시트와 같은 내용이다.

| 파일 | 역할 |
|---|---|
| `compare/questions.json` | 판정 질문 18개, 허용 판정값, 판정자(AI 판정 / AI 후보 / 자동) |
| `compare/common.py` | 질문 로드, 판정이 있어야 하는 (질문, 카드, 필수 정보) 조합 계산 |
| `providers/compare_judge.py` | `replay`(fixture, API 없음) / `vision`(카드 PNG + 원문 + 필수 정보 → 비전 LLM, 출력은 JSON 스키마로 고정) |
| `assertions/compare_judgment.py` | 판정 형식 검사(누락·허용값·근거·원문 인용 실재), 사람 판정 일치도 |
| `scripts/export_compare.py` | 결과를 평가표 '판정기록' 형식 CSV로 내보내고 사실성·완전성을 따로 요약 |
| `compare_smoke.yaml` | fixture smoke (`npm run smoke`에 포함) |
| `compare_vision.yaml` | 실제 판정 (OPENAI_API_KEY 필요) |

판정 원칙

- 시각·구성·결함 질문은 충족/미충족/해당 없음/판단 보류. 부분 충족은 미충족 (PresentBench, arXiv:2603.07244)
- 사실성(C-01)은 카드마다 뒷받침됨/왜곡 의심/근거 부족/판단 보류/주장 없음. 값과 세부 기준은 CardSync 카드 사실성 검사(`ai/verification/factuality/llm/f_prompt.md`)와 요약 사실성 검사(`ai/verification/consistency/prompts/consistency.md`)의 규칙을 그대로 쓴다. 기본 근거는 원문이다(망고보드에는 요약이 없고, 요약 단계 오류까지 잡기 위해). 요약 기준 판정은 아래 항목을 따른다. 틀린 문구마다 왜곡 의심/근거 부족을 따로 적는다
- 카드 단위와 세트 단위를 나눠 판정 (PPTEval, EMNLP 2025), 최종 PNG로 비교 (SlidesGen-Bench, arXiv:2601.09487)
- 사실성(C-01)과 완전성(C-02)은 합산하지 않고 따로 보고한다 (FineSurE, ACL 2024). 완전성은 필수 정보마다 전달/부분 전달/누락/왜곡이며, 판정값·정의·출력(해당 카드, 이유, 빠진 요소 목록)은 CardSync 완전성 검사(`ai/verification/completeness/llm/c_prompt.md`)의 COVERED/PARTIALLY_COVERED/MISSING/DISTORTED와 같다. 기준 목록만 다르다: 서비스 검사는 사용자가 선택한 그룹 요약, 비교 판정은 기사에서 생성 전에 뽑은 필수 정보(망고보드에는 선택 단계가 없고, 요약 단계의 누락까지 보기 위해). 부가 세부의 생략은 전달, 핵심 요소 일부가 빠지면 부분 전달, 값이 바뀌거나 조건을 빠뜨려 적용 범위가 바뀌면 왜곡이다. 부분 전달과 왜곡은 전달로 세지 않는다. 같은 오류가 C-01 왜곡 의심과 C-02 왜곡에 함께 잡힐 수 있다
- 요약 기준 판정(`basis: summary`): 기준을 원문·필수 정보 대신 CardSync 그룹 요약으로 쓰고, 망고보드 카드도 같은 요약으로 채점한다. `unit: mixed`면 사실성은 그룹 요약 단위로, 완전성은 요약 문장 하나를 한 항목(G4-2)으로 본다. 핵심·부가는 카드를 보기 전에 `scripts/tag_summary_sentences.py`로 요약만 보고 한 번 정해 `summary_tags_<기록 파일>.json`에 고정하고, 모든 서비스 판정에 같은 표시를 쓴다. `lenient_modifiers: true`는 완전성에서 꾸밈말만 빠진 경우를 전달로 보는 참고용 옵션이다
- C-01·C-02의 AI 판정은 후보다. 최종 판정은 사람이 한다. CardSync 검사기는 판정에 쓰지 않는다(자기 채점 방지)
- D-06(최소 글자 크기), D-07(저장 문구 일치)은 AI에게 묻지 않는다. CardSync는 렌더 화면 자동 측정, 망고보드 D-07은 해당 없음

사례 폴더 (`data/compare/`, git에 올리지 않음)

```
data/compare/a01/source.txt          원문 전체
data/compare/a01/facts.json          필수 정보 [{"id": "F1", "text": "..."}] — 생성 전에 확정
data/compare/a01/CardSync/*.png      카드 이미지, 파일 이름 순서 = 카드 순서
data/compare/a01/망고보드/*.png
```

실행

```sh
cd experiments/promptfoo
PROMPTFOO_PYTHON=<python> PYTHONPATH=../.. npx promptfoo eval -c compare_vision.yaml --no-cache --no-share -o results/compare_vision.json
cd ../.. && python -m experiments.promptfoo.scripts.export_compare experiments/promptfoo/results/compare_vision.json 판정기록.csv
```

카드 세트 1개(카드 6장, gpt-4.1-mini) 판정에 약 35초, 입력 약 16,000 / 출력 약 4,000 토큰, 약 $0.013이 들었다(11/6 연결 확인 1회). 이 비용은 평가용이며 서비스 비용과 따로 적는다.
