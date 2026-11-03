# promptfoo 활용 가이드 — CardSync 팀용

최종 수정일: 2026-11-03

이 문서는 레포에 구성한 promptfoo 환경을 팀원이 직접 실행하고, 새 평가를 추가하는 방법을 설명한다.
명령어는 이 브랜치에서 실제로 실행해 확인한 것만 적었다.

> **지금 되는 것과 안 되는 것**
>
> - 된다: API 키 없이 promptfoo를 실행하고, 우리 Python 함수(숫자 규칙, 판정 형식 검사)를 assertion으로 붙이고, 결과를 기대 판정과 비교하는 것.
> - 아직 안 된다: 실제 CardSync 요약 함수·직접 GPT 요약·비전 평가기 호출. 모델과 예산이 정해지지 않아 일부러 연결하지 않았다.
> - smoke 결과의 PASS/FAIL 비율은 **모델 성능이 아니다.** 연결이 제대로 됐는지만 확인한다.

## 1. promptfoo가 하는 일, 하지 않는 일

promptfoo는 "같은 입력을 여러 방식에 넣고, 같은 기준으로 채점해서, 결과를 나란히 보여주는" 실험 실행 도구다.

| 용어 | 우리 프로젝트에서의 의미 | 예 |
|---|---|---|
| **prompt / vars** | 각 사례에 넣는 입력 | 원문 `source`, 사례 ID `case_id` |
| **provider** | 출력을 만드는 쪽 | CardSync 요약 함수, 직접 GPT 요약, 비전 평가기 |
| **assertion** | 출력을 채점하는 규칙 | 원문에 없는 숫자가 생겼는가, 판정 JSON 형식이 맞는가 |
| **judge (llm-rubric 등)** | LLM이 채점하는 assertion | "이 요약은 원문과 같은 뜻인가?"를 LLM에게 묻기 |
| **정답(gold)** | 사람이 정한 기준 | mFACE 사람 판정 |

헷갈리기 쉬운 점:

- **promptfoo가 정답을 만들어주지 않는다.** llm-rubric 결과는 또 하나의 LLM 판정이지 사람 정답이 아니다. 검사기 정확도는 mFACE처럼 사람이 판정한 데이터와 비교해야 한다.
- **assertion 통과 = 내용이 맞다가 아니다.** 판정 형식 검사는 "평가기가 약속한 형식으로 답했는가"만 본다. 판정 내용이 맞는지는 따로 검증해야 한다.
- **비용·토큰은 provider가 알려준 만큼만 기록된다.** 우리 Python provider 안에서 여러 API를 부르면, 그 사용량을 합쳐서 `tokenUsage`·`cost`로 돌려줘야 화면에 나온다.

## 2. 처음 실행하기

### 준비물

- **Node 22.22 이상.** promptfoo 0.125.1이 요구한다. Node 20에서는 `Required: >=22.22.0` 메시지와 함께 실행되지 않는다.
  - 확인: `node --version`
  - macOS Homebrew: `brew install node@22` 후 `export PATH=/opt/homebrew/opt/node@22/bin:$PATH` (현재 터미널에만 적용)
- **레포 requirements가 설치된 Python 3.12.** assertion이 `ai/verification/consistency/numbers.py`를 불러오기 때문이다.

전역 설치(`npm install -g promptfoo`)는 하지 않는다. 버전이 사람마다 달라지기 때문이다. `package-lock.json`에 고정한 0.125.1을 `npm ci`로 설치한다.

### 실행

```sh
cd experiments/promptfoo
npm ci
PROMPTFOO_PYTHON=../../.venv/bin/python npm run smoke
```

`PROMPTFOO_PYTHON`에는 본인 가상환경의 python 경로를 넣는다.

### 정상 출력

```
== summary_smoke ==
  ✓ 2 passed (50.00%)
  ✗ 2 failed (50.00%)
  0 errors (0%)
확인한 기대 판정 8개, 문제 0개
== visual_smoke ==
  ✓ 1 passed (50.00%)
  ✗ 1 failed (50.00%)
  0 errors (0%)
확인한 기대 판정 2개, 문제 0개
```

**failed가 있어도 정상이다.** 규칙이 오류를 실제로 잡는지 보려고 일부러 틀린 사례를 넣었다.
통과 기준은 `문제 0개`와 종료 코드 0이다. `errors`가 0이 아니면 설치나 경로 문제다(7절 참고).

## 3. 결과 보기와 내보내기

```sh
cd experiments/promptfoo
npx promptfoo view        # 브라우저에서 결과 표 보기 (localhost)
```

- 결과 JSON은 `experiments/promptfoo/results/`에 저장된다. git에는 올라가지 않는다.
- 각 행의 `gradingResult.componentResults[].reason`에 실패 이유가 있다. 예: `원문에 없는 숫자: 970`
- 과거 실행 기록은 `~/.promptfoo/promptfoo.db`에 쌓인다. 팀원끼리 공유되지 않는다.
- `promptfoo share`나 웹 UI의 공유 기능은 결과를 외부 서버로 올린다. 원문 기사나 미공개 데이터가 들어간 결과는 공유하지 않는다. smoke 스크립트는 `--no-share`로 실행한다.

## 4. 현재 smoke가 확인하는 것

### 요약 비교 (`summary_smoke.yaml`)

같은 원문에 대해 두 provider의 출력을 숫자 규칙 두 개로 채점한다.

| 사례 | cardsync_fixture | direct_gpt_fixture | 확인하려는 것 |
|---|---|---|---|
| smoke_ev_subsidy | 숫자 그대로 → 통과 | 196 빠짐 → `keeps_source_numbers` 실패 | 누락 규칙이 빠진 숫자를 잡는가 |
| smoke_number_changed | 870→970 → `no_new_numbers` 실패 | 숫자 그대로 → 통과 | 변경 규칙이 바뀐 숫자를 잡는가 |

두 provider 모두 손으로 만든 fixture다. "CardSync가 GPT보다 낫다/못하다"를 뜻하지 않는다.

### 시각 평가 형식 (`visual_smoke.yaml`)

비전 평가기가 돌려줄 판정 JSON이 약속한 형식인지 검사한다.

- 모든 평가 항목에 결과가 있는가
- `card_ids`가 실제 카드 ID인가
- `verdict`가 `MET / NOT_MET / NOT_APPLICABLE / UNCERTAIN` 중 하나인가
- `NOT_APPLICABLE`에 이유가 있는가

일부러 망가뜨린 판정(`C9`, `GOOD`, 항목 누락)이 실패하는지까지 확인한다.

### 규칙이 진짜 작동하는지 확인한 방법

`no_new_numbers`가 항상 통과하도록 코드를 일부러 망가뜨리고 다시 돌렸을 때, 단위 테스트와 smoke 비교가 모두 실패하는 것을 확인했다. 기대 판정표와 비교하지 않고 "에러 없이 돌았다"만 보면 이런 고장을 놓친다.

## 5. 새 사례 추가하기

1. `fixtures/summary_outputs.json`에 사례 ID별 출력을 추가한다.
2. yaml의 `tests:`에 같은 `case_id`와 `source`를 추가한다.
3. `expected/summary_smoke.json`에 사례·provider·metric별 기대 PASS/FAIL을 적는다.
4. `npm run smoke` 실행.

기대 판정을 적지 않으면 `check_results.py`가 그 사례를 확인하지 않는다. 결과를 본 뒤 기대값을 결과에 맞춰 고치면 검사가 의미 없어진다. 기대값은 실행 전에 적는다.

## 6. 실제 비교로 넘어갈 때 (아직 하지 않은 작업)

모델과 예산을 정한 다음에 진행한다.

### 요약 비교: CardSync vs 직접 GPT

- `providers/replay.py` 대신 실제 함수를 부르는 provider를 만든다. CardSync 쪽은 `ai/analysis/summarizer.py` 경로를 그대로 호출한다.
- 직접 GPT에도 **같은 목적과 보존 조건**을 준다. CardSync Summary는 정보 보존용 중간 자료라서, 짧게 요약하라고 시킨 GPT와 압축률만으로 비교하면 공정하지 않다.
- 두 provider는 같은 모델로 먼저 비교한다. 모델까지 바꾸면 차이가 구조 때문인지 모델 때문인지 알 수 없다.
- 사실성 판정 정확도는 mFACE 사람 판정과 비교한다. promptfoo assertion 통과율을 정확도라고 부르지 않는다.

### 시각 평가: CardSync vs 망고보드

- 망고보드 결과는 사람이 만들어 PNG로 저장한다. promptfoo가 망고보드를 조작하지 않는다.
- 비전 평가기는 promptfoo 없이도 호출 가능한 Python 함수로 만들고, provider는 그 함수를 감싸기만 한다.
- `visual_judgment.py`의 형식 검사는 그대로 쓴다.
- 평가 설계는 옵시디언 `2026-11-03 시각 평가기 구현 전달서` 문서를 따른다.

### 유료 API를 연결할 때 지킬 것

- 키는 `.env`에 두고 커밋하지 않는다. `--env-file .env`로 읽는다.
- `--max-concurrency`를 낮게 두고, 사례 몇 개로 먼저 돌려 실제 사용량을 확인한 뒤 전체를 돌린다.
- **`llm-rubric`을 쓰면 별도 채점 모델이 호출된다.** 채점 모델을 지정하지 않으면 환경에 있는 키에 따라 기본 모델이 쓰이므로, `provider`를 명시한다. 채점 비용은 서비스 비용과 따로 기록한다.
- 캐시는 같은 요청의 재호출을 막아 비용을 줄이지만, 반복 실행 안정성을 볼 때는 `--no-cache`로 새로 호출해야 한다.
- CI에는 유료 평가를 넣지 않는다. CI는 지금처럼 fixture smoke만 돌린다.

## 7. 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| `npx promptfoo`가 `Required: >=22.22.0`을 내고 멈춤 | Node 22.22 미만. `node --version` 확인 후 Node 22로 실행 |
| `errors`가 0이 아니고 `ModuleNotFoundError` | `PROMPTFOO_PYTHON`이 requirements 미설치 python을 가리킴. 가상환경 python 경로를 넣는다 |
| `No module named 'ai'` | 레포 루트가 Python 경로에 없음. `npm run smoke`로 실행하면 스크립트가 설정한다 |
| `결과 없음: ...` | yaml의 `metric` 이름, provider `label`, `case_id`가 expected 파일과 다름 |
| `기대와 다름: ...` | 규칙이 바뀌었거나 fixture가 바뀜. 규칙 변경이 의도된 것인지 먼저 확인 |
| 결과가 이전 실행과 같음 | 캐시. `--no-cache` 사용 (smoke는 기본 적용) |

## 8. 참고한 자료

- [LLM 앱 테스트 방법: Promptfoo 완벽 가이드 (2026년), DEV Community](https://dev.to/rihpig/llm-aeb-teseuteu-bangbeob-promptfoo-wanbyeog-gaideu-2026nyeon-12b8). 0.121.2 기준이고 이 환경은 0.125.1이다.
  - 가져온 것: 구성 파일 구조(prompts·providers·tests), assertion 종류, `--no-cache`·`--output`·`--max-concurrency` 플래그, 결과 DB·캐시 위치, 신뢰 모델(설정과 Python 코드는 실행되는 코드로 취급).
  - 그대로 따르지 않은 것:
    - **"100% 로컬 실행"**: promptfoo 자체는 로컬에서 돌지만, 외부 모델 provider나 llm-rubric을 쓰면 프롬프트와 원문이 해당 API로 전송된다. 공유 기능도 외부로 올린다.
    - **전역 설치**: 버전 고정을 위해 lockfile + `npm ci`를 쓴다.
    - **CI에 API 키 secrets 넣기**: 유료 호출과 비용 통제를 이유로 CI는 fixture만 돌린다.
    - **합격률 threshold 게이트**: smoke에는 일부러 실패하는 사례가 있어 합격률이 품질을 뜻하지 않는다. 대신 사례별 기대 판정과 비교한다.
    - **레드팀·코드 스캔**: 이번 프로젝트 평가 범위 밖이다.
    - **도입 사례의 개선 수치**(이슈 90% 감소 등): 해당 글의 주장이며 우리 결과가 아니다.
- promptfoo 공식 문서
  - [Python provider](https://www.promptfoo.dev/docs/providers/python/)
  - [Python assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/python/)
  - [LLM rubric](https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/llm-rubric/)
