"""PostgreSQL 저장소. 행 하나에 JSON을 담는 단순 구조로 두고, 조회 조건에 쓰는 열만 따로 뺀다."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

# Supabase는 public 표를 Data API로 노출하므로 RLS를 켜 둔다. 서버는 소유자 역할이라 영향이 없다.
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_user_id ON documents (user_id);
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, ord INTEGER NOT NULL, data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_document_id ON cards (document_id);
CREATE TABLE IF NOT EXISTS checks (
    card_id TEXT NOT NULL, card_version INTEGER NOT NULL, data JSONB NOT NULL,
    PRIMARY KEY (card_id, card_version)
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, user_id TEXT NOT NULL, data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_document_id ON jobs (document_id);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Store:
    def __init__(self, url: str):
        # 풀이 연결을 스레드마다 나눠 주므로 BackgroundTasks에서 불러도 안전하다
        self._pool = ConnectionPool(
            url, min_size=1, max_size=4, check=ConnectionPool.check_connection, open=True
        )
        with self._pool.connection() as db:
            db.execute(SCHEMA)
            # 이전 프로세스에서 돌던 작업은 이어서 실행할 수 없다
            db.execute(
                """UPDATE jobs SET data = data || jsonb_build_object(
                       'status', 'failed',
                       'error', jsonb_build_object(
                           'type', 'ServerRestarted', 'stage', data->'stage'))
                   WHERE data->>'status' IN ('queued', 'running')"""
            )

    def close(self) -> None:
        self._pool.close()

    def _one(self, sql: str, params: tuple) -> dict | None:
        with self._pool.connection() as db:
            row = db.execute(sql, params).fetchone()
        return row[0] if row else None

    def _write(self, sql: str, params: tuple) -> None:
        with self._pool.connection() as db:
            db.execute(sql, params)

    # documents
    def get_document(self, document_id: str) -> dict | None:
        return self._one("SELECT data FROM documents WHERE id=%s", (document_id,))

    def save_document(self, doc: dict) -> None:
        self._write(
            """INSERT INTO documents (id, user_id, data) VALUES (%s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data""",
            (doc["document_id"], doc["user_id"], Jsonb(doc)),
        )

    # jobs
    def get_job(self, job_id: str, user_id: str) -> dict | None:
        return self._one("SELECT data FROM jobs WHERE id=%s AND user_id=%s", (job_id, user_id))

    def save_job(self, job: dict) -> None:
        # 작업 주인은 문서 주인과 같다
        self._write(
            """INSERT INTO jobs (id, document_id, user_id, data)
               VALUES (%s, %s, (SELECT user_id FROM documents WHERE id=%s), %s)
               ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data""",
            (job["job_id"], job["document_id"], job["document_id"], Jsonb(job)),
        )

    def active_job(self, document_id: str) -> dict | None:
        return self._one(
            """SELECT data FROM jobs
               WHERE document_id=%s AND data->>'status' IN ('queued', 'running') LIMIT 1""",
            (document_id,),
        )

    # cards
    def list_cards(self, document_id: str) -> list[dict]:
        with self._pool.connection() as db:
            rows = db.execute(
                "SELECT data FROM cards WHERE document_id=%s ORDER BY ord", (document_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_card(self, card_id: str) -> dict | None:
        return self._one("SELECT data FROM cards WHERE id=%s", (card_id,))

    def replace_cards(self, document_id: str, cards: list[dict]) -> None:
        with self._pool.connection() as db:  # 블록 하나가 트랜잭션 하나다
            db.execute(
                "DELETE FROM checks WHERE card_id IN (SELECT id FROM cards WHERE document_id=%s)",
                (document_id,),
            )
            db.execute("DELETE FROM cards WHERE document_id=%s", (document_id,))
            db.cursor().executemany(
                "INSERT INTO cards (id, document_id, ord, data) VALUES (%s, %s, %s, %s)",
                [(c["db_id"], document_id, c["order"], Jsonb(c)) for c in cards],
            )

    def save_card(self, card: dict) -> None:
        self._write("UPDATE cards SET data=%s WHERE id=%s", (Jsonb(card), card["db_id"]))

    # checks
    def save_check(self, db_id: str, check: dict) -> None:
        self._write(
            """INSERT INTO checks (card_id, card_version, data) VALUES (%s, %s, %s)
               ON CONFLICT (card_id, card_version) DO UPDATE SET data = EXCLUDED.data""",
            (db_id, check["card_version"], Jsonb(check)),
        )

    def latest_check(self, db_id: str) -> dict | None:
        return self._one(
            "SELECT data FROM checks WHERE card_id=%s ORDER BY card_version DESC LIMIT 1",
            (db_id,),
        )
