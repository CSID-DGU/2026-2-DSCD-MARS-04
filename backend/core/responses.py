"""공통 응답 형식 {code, message, data}와 API 오류."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


def ok(message: str, data: Any = None, code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=code, content={"code": code, "message": message, "data": data})


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.code, content={"code": exc.code, "message": exc.message})


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # 입력값(원문 등)을 응답에 되돌려 주지 않고 위치와 이유만 알린다
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    message = f"요청 형식이 올바르지 않습니다: {where} {first.get('msg', '')}".strip()
    return JSONResponse(status_code=400, content={"code": 400, "message": message})
