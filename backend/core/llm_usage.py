"""작업 단계별 LLM 토큰 사용량 집계.

팀원 AI 코드는 고치지 않는다는 원칙 때문에, 모든 호출이 지나는 OpenAI SDK의
Responses.parse를 한 번 감싸서 응답의 usage를 현재 단계 집계에 더한다.
클라이언트를 바꾸지 않으므로 모듈별 timeout·재시도 설정은 그대로다.
"""

from __future__ import annotations

import contextvars

from openai.resources.responses import Responses

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("llm_usage", default=None)


def start() -> dict:
    """새 집계를 시작하고 반환한다. 이 컨텍스트에서 일어난 parse 호출이 여기에 쌓인다."""
    acc = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}
    _current.set(acc)
    return acc


def add(response) -> None:
    acc, usage = _current.get(), getattr(response, "usage", None)
    if acc is None or usage is None:
        return
    acc["llm_calls"] += 1
    acc["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
    acc["output_tokens"] += getattr(usage, "output_tokens", 0) or 0


def _wrap(parse):
    def wrapped(self, *args, **kwargs):
        response = parse(self, *args, **kwargs)
        add(response)
        return response

    wrapped.__wrapped__ = parse
    return wrapped


# shortcut: AI 코드가 responses.parse만 쓴다(11/9 기준 9곳).
# create·chat.completions를 쓰기 시작하면 같이 감싼다.
if not hasattr(Responses.parse, "__wrapped__"):
    Responses.parse = _wrap(Responses.parse)
