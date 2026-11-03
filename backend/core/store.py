"""SQLite 저장소. 행 하나에 JSON을 담는 단순 구조로 두고, 조회 조건에 쓰는 열만 따로 뺀다."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, ord INTEGER NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    card_id TEXT NOT NULL, card_version INTEGER NOT NULL, data TEXT NOT NULL,
    PRIMARY KEY (card_id, card_version)
);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, document_id TEXT, data TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Store:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            # 이전 프로세스에서 돌던 작업은 이어서 실행할 수 없다
            for job_id, raw in self._db.execute("SELECT id, data FROM jobs").fetchall():
                job = json.loads(raw)
                if job["status"] in ("queued", "running"):
                    job.update(
                        status="failed",
                        error={"type": "ServerRestarted", "stage": job.get("stage")},
                    )
                    self._db.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(job), job_id))
            self._db.commit()

    def _get(self, table: str, key: str) -> dict | None:
        with self._lock:
            row = self._db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    # documents
    def get_document(self, document_id: str) -> dict | None:
        return self._get("documents", document_id)

    def save_document(self, doc: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?)",
                (doc["document_id"], json.dumps(doc, ensure_ascii=False)),
            )
            self._db.commit()

    # jobs
    def get_job(self, job_id: str) -> dict | None:
        return self._get("jobs", job_id)

    def save_job(self, job: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)",
                (job["job_id"], job["document_id"], json.dumps(job, ensure_ascii=False)),
            )
            self._db.commit()

    def active_job(self, document_id: str) -> dict | None:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM jobs WHERE document_id=?", (document_id,)
            ).fetchall()
        for (raw,) in rows:
            job = json.loads(raw)
            if job["status"] in ("queued", "running"):
                return job
        return None

    # cards
    def list_cards(self, document_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM cards WHERE document_id=? ORDER BY ord", (document_id,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get_card(self, card_id: str) -> dict | None:
        return self._get("cards", card_id)

    def replace_cards(self, document_id: str, cards: list[dict]) -> None:
        with self._lock:
            old = [
                r[0]
                for r in self._db.execute(
                    "SELECT id FROM cards WHERE document_id=?", (document_id,)
                )
            ]
            self._db.executemany("DELETE FROM checks WHERE card_id=?", [(i,) for i in old])
            self._db.execute("DELETE FROM cards WHERE document_id=?", (document_id,))
            self._db.executemany(
                "INSERT INTO cards VALUES (?, ?, ?, ?)",
                [
                    (c["db_id"], document_id, c["order"], json.dumps(c, ensure_ascii=False))
                    for c in cards
                ],
            )
            self._db.commit()

    def save_card(self, card: dict) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE cards SET data=? WHERE id=?",
                (json.dumps(card, ensure_ascii=False), card["db_id"]),
            )
            self._db.commit()

    # checks
    def save_check(self, db_id: str, check: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO checks VALUES (?, ?, ?)",
                (db_id, check["card_version"], json.dumps(check, ensure_ascii=False)),
            )
            self._db.commit()

    def latest_check(self, db_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM checks WHERE card_id=? ORDER BY card_version DESC LIMIT 1",
                (db_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None
