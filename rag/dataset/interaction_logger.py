from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import aiosqlite


@dataclass
class InteractionRecord:
    interaction_id: str
    namespace: str
    query: str
    rewritten_query: str
    intent: str
    response: str
    model_used: str
    routing: str
    chunk_ids: list[str]
    eval_score: float | None = None
    user_rating: int | None = None
    latency_ms: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    context_text: str = ""


class InteractionLogger:
    """모든 Q&A 인터랙션을 SQLite에 기록합니다."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS interactions (
                    interaction_id  TEXT PRIMARY KEY,
                    namespace       TEXT,
                    query           TEXT NOT NULL,
                    rewritten_query TEXT DEFAULT '',
                    intent          TEXT DEFAULT '',
                    response        TEXT NOT NULL,
                    model_used      TEXT DEFAULT '',
                    routing         TEXT DEFAULT '',
                    chunk_ids       TEXT DEFAULT '[]',
                    eval_score      REAL,
                    user_rating     INTEGER,
                    latency_ms      INTEGER DEFAULT 0,
                    created_at      TEXT,
                    context_text    TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS eval_scores (
                    eval_id         TEXT PRIMARY KEY,
                    interaction_id  TEXT REFERENCES interactions(interaction_id),
                    scorer          TEXT NOT NULL,
                    score           REAL NOT NULL,
                    feedback        TEXT DEFAULT '',
                    created_at      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_interactions_namespace
                    ON interactions(namespace);
                CREATE INDEX IF NOT EXISTS idx_interactions_rating
                    ON interactions(user_rating);
                CREATE INDEX IF NOT EXISTS idx_interactions_created
                    ON interactions(created_at);
            """)
            await db.commit()

    async def log(self, record: InteractionRecord) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO interactions
                   (interaction_id, namespace, query, rewritten_query, intent,
                    response, model_used, routing, chunk_ids,
                    eval_score, user_rating, latency_ms, created_at, context_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.interaction_id, record.namespace,
                    record.query, record.rewritten_query, record.intent,
                    record.response, record.model_used, record.routing,
                    json.dumps(record.chunk_ids),
                    record.eval_score, record.user_rating,
                    record.latency_ms, record.created_at,
                    record.context_text,
                ),
            )
            await db.commit()
        return record.interaction_id

    async def update_eval_score(self, interaction_id: str, score: float, scorer_scores: dict[str, float]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE interactions SET eval_score = ? WHERE interaction_id = ?",
                (score, interaction_id),
            )
            for scorer, s in scorer_scores.items():
                await db.execute(
                    """INSERT INTO eval_scores (eval_id, interaction_id, scorer, score, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), interaction_id, scorer, s,
                     datetime.utcnow().isoformat()),
                )
            await db.commit()

    async def update_rating(self, interaction_id: str, rating: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE interactions SET user_rating = ? WHERE interaction_id = ?",
                (rating, interaction_id),
            )
            await db.commit()

    async def query_interactions(
        self,
        namespace: str | None = None,
        min_rating: int | None = None,
        min_eval_score: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InteractionRecord]:
        conditions = ["1=1"]
        params: list = []
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)
        if min_rating is not None:
            conditions.append("user_rating >= ?")
            params.append(min_rating)
        if min_eval_score is not None:
            conditions.append("eval_score >= ?")
            params.append(min_eval_score)

        where = " AND ".join(conditions)
        params += [limit, offset]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM interactions WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_record(r) for r in rows]

    def _row_to_record(self, row) -> InteractionRecord:
        return InteractionRecord(
            interaction_id=row["interaction_id"],
            namespace=row["namespace"] or "",
            query=row["query"],
            rewritten_query=row["rewritten_query"] or "",
            intent=row["intent"] or "",
            response=row["response"],
            model_used=row["model_used"] or "",
            routing=row["routing"] or "",
            chunk_ids=json.loads(row["chunk_ids"] or "[]"),
            eval_score=row["eval_score"],
            user_rating=row["user_rating"],
            latency_ms=row["latency_ms"] or 0,
            created_at=row["created_at"] or "",
            context_text=row["context_text"] or "",
        )
