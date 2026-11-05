"""Unsplash 사진 검색. 생성 에이전트가 낸 image_query 로 첫 장을 고른다.

가이드라인: 사진을 쓸 때 download_location 을 호출(다운로드 집계)하고, 작가·Unsplash 크레딧을
utm 링크와 함께 표기한다. Access Key 만 쓴다(Secret Key 는 OAuth 전용). 키는 .env 에만 둔다.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.unsplash.com"
UTM = "utm_source=cardsync&utm_medium=referral"
TIMEOUT = 10


def _get(url: str, key: str) -> Any:
    import json

    req = Request(url, headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"})
    with urlopen(req, timeout=TIMEOUT) as res:  # noqa: S310 — https 고정
        return json.loads(res.read().decode("utf-8"))


def search_photo(query: str, *, key: str | None = None) -> dict | None:
    """검색 첫 장을 카드 image 필드 모양으로 돌려준다. 키가 없거나 결과가 없으면 None."""
    key = key or os.getenv("UNSPLASH_ACCESS_KEY")
    if not key or not query.strip():
        return None
    params = urlencode(
        {"query": query, "per_page": 1, "orientation": "portrait", "content_filter": "high"}
    )
    data = _get(f"{API}/search/photos?{params}", key)
    results = data.get("results") or []
    if not results:
        return None
    p = results[0]
    user = p.get("user") or {}
    try:
        _get(p["links"]["download_location"], key)  # 다운로드 집계 (가이드라인 필수)
    except Exception:  # noqa: BLE001 — 집계 실패는 사진 사용을 막지 않는다
        pass
    return {
        "stage": "unsplash",
        "id": p.get("id"),
        "query": query,
        "data": p["urls"].get("regular"),
        "alt": p.get("alt_description") or "",
        "author": user.get("name") or "",
        "author_url": f"{user.get('links', {}).get('html', '')}?{UTM}",
        "photo_url": f"{p.get('links', {}).get('html', '')}?{UTM}",
        "license": "Unsplash License",
    }
