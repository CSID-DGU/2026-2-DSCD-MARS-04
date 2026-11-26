import os

import psycopg
import pytest

from backend.core.store import Store


@pytest.fixture
def store():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL이 없습니다. 테스트용 PostgreSQL 주소를 넣어 주세요.")
    # 테스트가 표를 지우므로 운영 DB를 가리키면 멈춘다
    if url == os.environ.get("DATABASE_URL") or "supabase" in url:
        pytest.fail("TEST_DATABASE_URL이 운영 DB를 가리킵니다.")
    with psycopg.connect(url) as db:
        db.execute("DROP TABLE IF EXISTS documents, cards, checks, jobs")
    s = Store(url)
    yield s
    s.close()
