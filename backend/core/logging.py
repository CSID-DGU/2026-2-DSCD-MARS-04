"""요청 ID와 JSON 구조 로그.

- 요청마다 request_id를 정하고(형식이 맞는 X-Request-ID는 그대로 사용) 응답 헤더로 돌려준다.
- 요청 한 건 = JSON 한 줄. 경로는 템플릿(/api/v1/documents/{document_id})으로 남겨
  집계할 수 있게 한다.
- 원문·요청 본문·쿼리 문자열·헤더 값·API 키는 남기지 않는다. 원문이 개인정보를 담을 수 있고
  오류 메시지에 키가 섞일 수 있어서다(레포 ai/ 모듈의 로그 규칙과 같다).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from starlette.routing import Match

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

logger = logging.getLogger("cardsync")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    if any(getattr(h, "_cardsync", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._cardsync = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def log(event: str, level: int = logging.INFO, **fields) -> None:
    rid = fields.pop("request_id", None) or _request_id.get()
    if rid:
        fields = {"request_id": rid, **fields}
    logger.log(level, event, extra={"fields": fields})


def current_request_id() -> str | None:
    return _request_id.get()


def new_request_id(candidate: str | None) -> str:
    if candidate and _VALID_ID.match(candidate):
        return candidate
    return uuid4().hex


def _route_template(scope) -> str:
    """매칭된 라우트의 경로 템플릿.

    매칭이 없으면 실제 경로 대신 고정 문자열을 남긴다(탐색 요청 경로를 기록하지 않음).
    """
    app = scope.get("app")
    for route in getattr(getattr(app, "router", None), "routes", []):
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", "unknown")
    return "<unmatched>"


class RequestLogMiddleware:
    """순수 ASGI 미들웨어. 응답 헤더에 request_id를 넣고 요청 한 건을 JSON 한 줄로 남긴다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        rid = new_request_id(headers.get(REQUEST_ID_HEADER.lower()))
        token = _request_id.set(rid)
        started = time.perf_counter()
        status = {"code": 500}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (REQUEST_ID_HEADER.lower().encode(), rid.encode())
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            code = status["code"]
            log(
                "http_request",
                logging.ERROR if code >= 500 else logging.INFO,
                method=scope.get("method"),
                route=_route_template(scope),
                status=code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            _request_id.reset(token)
