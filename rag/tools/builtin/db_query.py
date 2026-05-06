from __future__ import annotations

import aiosqlite

from ..registry import ToolDefinition


async def _db_query_handler(query: str, db_path: str = ":memory:") -> list[dict]:
    """SQLite 데이터베이스를 조회합니다 (SELECT만 허용)."""
    query_lower = query.strip().lower()
    if not query_lower.startswith("select"):
        raise ValueError("SELECT 쿼리만 허용됩니다.")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def db_query_tool() -> ToolDefinition:
    return ToolDefinition(
        name="db_query",
        description="SQLite 데이터베이스에 SELECT 쿼리를 실행합니다.",
        parameters={
            "query": {"type": "string", "description": "실행할 SELECT SQL 쿼리"},
            "db_path": {"type": "string", "description": "SQLite 데이터베이스 파일 경로"},
        },
        handler=_db_query_handler,
    )
