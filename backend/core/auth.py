from __future__ import annotations

import os
from functools import cache
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.responses import ApiError

_bearer = HTTPBearer(auto_error=False)


@cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{_issuer()}/.well-known/jwks.json")


def _issuer() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1"


def current_user(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Supabase 액세스 토큰을 검증하고 user_id(sub)를 돌려준다."""
    if cred is None:
        raise ApiError(401, "로그인이 필요합니다.")
    token = cred.credentials
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=_issuer(),
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWKClientConnectionError:
        raise ApiError(503, "로그인 확인 서버에 연결하지 못했습니다.") from None
    except jwt.PyJWTError:
        raise ApiError(401, "로그인 정보가 올바르지 않습니다. 다시 로그인해 주세요.") from None
    return claims["sub"]


UserDep = Annotated[str, Depends(current_user)]
