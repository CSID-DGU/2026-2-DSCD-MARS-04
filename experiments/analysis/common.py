"""그룹화·요약 비교 실험이 같이 쓰는 부분: 모델 호출, 기사 고르기, 결과 저장.

실험용 추가 설치: pip install anthropic scikit-learn

모델은 "이름@temperature#생각정도"로 적는다. 뒤의 두 부분은 생략할 수 있다.
  gpt-4.1-mini@0      temperature 0
  gpt-6-luna@0        생각 끔(기본) + temperature 0
  gpt-6-luna#low      생각 low (이때는 temperature 지정 불가)
  claude-haiku-5-5    Claude는 temperature·생각 정도를 지정하지 않는다
"""

import csv
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.sentence_splitter import split_sentences

RESULT_DIR = Path(__file__).with_name("results")
MAX_OUTPUT_TOKENS = 8000

# 100만 토큰당 (입력, 출력) 달러.
PRICES = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-6-luna": (0.10, 0.50),
    "claude-haiku-5-5": (0.10, 0.50),
}


# ── 모델 호출 ───────────────────────────────────────────────


def parse_spec(spec):
    """'gpt-6-luna@0' → ('gpt-6-luna', 0.0, None), 'gpt-6-luna#low' → ('gpt-6-luna', None, 'low')"""
    rest, _, effort = spec.partition("#")
    name, _, temperature = rest.partition("@")
    if name.startswith("claude") and (temperature or effort):
        raise ValueError(f"Claude는 temperature나 생각 정도를 지정할 수 없습니다: {spec}")
    if effort and not name.startswith(("gpt-5", "gpt-6")):
        raise ValueError(f"생각 정도는 gpt-5·gpt-6 계열만 지정할 수 있습니다: {spec}")
    if effort and effort != "none" and temperature:
        raise ValueError(f"생각을 켜면 temperature를 지정할 수 없습니다: {spec}")
    return name, float(temperature) if temperature else None, effort or None


def call_openai(model, temperature, effort, prompt, user_input, schema):
    from openai import OpenAI

    extra = {} if temperature is None else {"temperature": temperature}
    if model.startswith(("gpt-5", "gpt-6")):
        # 기본은 생각 끔: 4.1-mini와 조건을 맞추고 temperature를 쓸 수 있게 함
        extra["reasoning"] = {"effort": effort or "none"}
    response = OpenAI().responses.parse(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        text_format=schema,
        **extra,
    )
    if response.output_parsed is None:
        raise RuntimeError("스키마에 맞는 결과가 없습니다.")
    usage = response.usage
    return response.output_parsed, usage.input_tokens, usage.output_tokens, response.model


def call_anthropic(model, temperature, effort, prompt, user_input, schema):
    from anthropic import Anthropic

    response = Anthropic().messages.parse(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=prompt,
        messages=[{"role": "user", "content": user_input}],
        output_format=schema,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"스키마에 맞는 결과가 없습니다 ({response.stop_reason}).")
    usage = response.usage
    return response.parsed_output, usage.input_tokens, usage.output_tokens, response.model


def call_model(spec, prompt, user_input, schema, usage):
    """호출 결과를 돌려주고, 토큰·시간은 usage에 더한다."""
    model, temperature, effort = parse_spec(spec)
    caller = call_anthropic if model.startswith("claude") else call_openai
    started = time.perf_counter()
    parsed, input_tokens, output_tokens, response_model = caller(
        model, temperature, effort, prompt, user_input, schema
    )
    usage["input_tokens"] = usage.get("input_tokens", 0) + input_tokens
    usage["output_tokens"] = usage.get("output_tokens", 0) + output_tokens
    usage["latency_seconds"] = usage.get("latency_seconds", 0) + time.perf_counter() - started
    usage["response_model"] = response_model
    usage["calls"] = usage.get("calls", 0) + 1
    return parsed


def cost_per_article(spec, tokens_in, tokens_out, articles):
    price = PRICES.get(parse_spec(spec)[0])
    if price is None or not articles:
        return None
    return round((tokens_in * price[0] + tokens_out * price[1]) / 1e6 / articles, 5)


# ── 기사 고르기와 결과 저장 ─────────────────────────────────


def pick_articles(path, n):
    """문장 수 순으로 정렬한 뒤 고르게 뽑아 짧은·중간·긴 기사가 섞이게 한다."""
    articles = []
    for article in load_articles(path, limit=10_000):
        sentences = split_sentences(article["source_text"])
        if len(sentences) >= 3:
            articles.append({**article, "sentences": sentences})
    articles.sort(key=lambda a: len(a["sentences"]))
    if n >= len(articles):
        return articles
    step = len(articles) / n
    return [articles[int(i * step)] for i in range(n)]


def make_run_dir(prefix):
    run_dir = RESULT_DIR / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_results(run_dir, rows, config):
    """summary.csv와 config.json을 저장하고 표를 출력한다."""
    with (run_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (run_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    keys = list(rows[0])
    if len(rows) <= 4:  # 조건이 적으면 조건을 열로
        for key in keys:
            print(f"{key:26s}" + "".join(f"{str(row[key]):>20s}" for row in rows))
    else:  # 많으면 조건을 행으로
        print("  ".join(f"{k:>18s}" for k in keys))
        for row in rows:
            print("  ".join(f"{str(row[k]):>18s}" for k in keys))
    print(f"\n결과 폴더: {run_dir}")


def mean(values, digits=3):
    values = list(values)
    return round(statistics.mean(values), digits) if values else None


def rate(part, whole):
    return round(part / whole, 3) if whole else None
