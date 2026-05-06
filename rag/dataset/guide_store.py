from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiosqlite


@dataclass
class GuideRecord:
    guide_id: str
    name: str
    source_file: str = ""
    page_count: int = 0
    status: str = "parsing"   # parsing | extracting | done | failed
    progress: int = 0         # 0~100
    error_msg: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class RuleRecord:
    rule_id: str
    guide_id: str
    section_label: str = ""
    title: str = ""
    body: str = ""
    category: str = "기타"
    severity: str = "unknown"      # must / should / may / unknown
    code_bad: str = ""
    code_good: str = ""
    source_pages: str = ""         # "12,13,14"
    order_index: int = 0
    reviewed: int = 0
    user_edited: int = 0
    deleted: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class GeneratedQARecord:
    qa_id: str
    rule_id: str
    guide_id: str
    qa_type: str                   # code_review / code_gen / concept / refusal
    instruction: str = ""
    output: str = ""
    status: str = "pending"        # pending / approved / rejected
    user_edited: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class GuideStore:
    """가이드 + 추출된 규칙을 SQLite에 저장합니다."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS guides (
                    guide_id    TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    source_file TEXT DEFAULT '',
                    page_count  INTEGER DEFAULT 0,
                    status      TEXT DEFAULT 'parsing',
                    progress    INTEGER DEFAULT 0,
                    error_msg   TEXT DEFAULT '',
                    created_at  TEXT,
                    updated_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS rules (
                    rule_id        TEXT PRIMARY KEY,
                    guide_id       TEXT REFERENCES guides(guide_id) ON DELETE CASCADE,
                    section_label  TEXT DEFAULT '',
                    title          TEXT DEFAULT '',
                    body           TEXT DEFAULT '',
                    category       TEXT DEFAULT '기타',
                    severity       TEXT DEFAULT 'unknown',
                    code_bad       TEXT DEFAULT '',
                    code_good      TEXT DEFAULT '',
                    source_pages   TEXT DEFAULT '',
                    order_index    INTEGER DEFAULT 0,
                    reviewed       INTEGER DEFAULT 0,
                    user_edited    INTEGER DEFAULT 0,
                    deleted        INTEGER DEFAULT 0,
                    created_at     TEXT
                );

                CREATE TABLE IF NOT EXISTS generated_qa (
                    qa_id        TEXT PRIMARY KEY,
                    rule_id      TEXT REFERENCES rules(rule_id) ON DELETE CASCADE,
                    guide_id     TEXT REFERENCES guides(guide_id) ON DELETE CASCADE,
                    qa_type      TEXT DEFAULT 'code_review',
                    instruction  TEXT NOT NULL,
                    output       TEXT NOT NULL,
                    status       TEXT DEFAULT 'pending',
                    user_edited  INTEGER DEFAULT 0,
                    created_at   TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_rules_guide ON rules(guide_id);
                CREATE INDEX IF NOT EXISTS idx_rules_category ON rules(category);
                CREATE INDEX IF NOT EXISTS idx_guides_status ON guides(status);
                CREATE INDEX IF NOT EXISTS idx_qa_rule ON generated_qa(rule_id);
                CREATE INDEX IF NOT EXISTS idx_qa_guide ON generated_qa(guide_id);
                CREATE INDEX IF NOT EXISTS idx_qa_status ON generated_qa(status);
            """)
            await db.commit()

    # --- guides --------------------------------------------------------

    async def create_guide(self, name: str, source_file: str) -> str:
        guide_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO guides
                   (guide_id, name, source_file, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'parsing', ?, ?)""",
                (guide_id, name, source_file, now, now),
            )
            await db.commit()
        return guide_id

    async def update_guide_status(
        self,
        guide_id: str,
        status: str | None = None,
        progress: int | None = None,
        page_count: int | None = None,
        error_msg: str | None = None,
    ) -> None:
        sets = ["updated_at = ?"]
        params: list = [datetime.utcnow().isoformat()]
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if progress is not None:
            sets.append("progress = ?")
            params.append(progress)
        if page_count is not None:
            sets.append("page_count = ?")
            params.append(page_count)
        if error_msg is not None:
            sets.append("error_msg = ?")
            params.append(error_msg)
        params.append(guide_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE guides SET {', '.join(sets)} WHERE guide_id = ?",
                params,
            )
            await db.commit()

    async def list_guides(self) -> list[GuideRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guides ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_guide(r) for r in rows]

    async def get_guide(self, guide_id: str) -> GuideRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guides WHERE guide_id = ?", (guide_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return self._row_to_guide(row) if row else None

    async def delete_guide(self, guide_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM rules WHERE guide_id = ?", (guide_id,))
            cursor = await db.execute(
                "DELETE FROM guides WHERE guide_id = ?", (guide_id,)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def count_rules(self, guide_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM rules WHERE guide_id = ? AND deleted = 0",
                (guide_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return int(row[0]) if row else 0

    # --- rules ---------------------------------------------------------

    async def insert_rule(self, rule: RuleRecord) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO rules
                   (rule_id, guide_id, section_label, title, body, category, severity,
                    code_bad, code_good, source_pages, order_index,
                    reviewed, user_edited, deleted, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.rule_id, rule.guide_id, rule.section_label, rule.title,
                    rule.body, rule.category, rule.severity,
                    rule.code_bad, rule.code_good, rule.source_pages,
                    rule.order_index, rule.reviewed, rule.user_edited, rule.deleted,
                    rule.created_at,
                ),
            )
            await db.commit()
        return rule.rule_id

    async def list_rules(
        self,
        guide_id: str,
        category: str | None = None,
        severity: str | None = None,
        include_deleted: bool = False,
    ) -> list[RuleRecord]:
        conditions = ["guide_id = ?"]
        params: list = [guide_id]
        if not include_deleted:
            conditions.append("deleted = 0")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        where = " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM rules WHERE {where} ORDER BY order_index ASC, created_at ASC",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_rule(r) for r in rows]

    async def get_rule(self, rule_id: str) -> RuleRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM rules WHERE rule_id = ?", (rule_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return self._row_to_rule(row) if row else None

    async def update_rule(self, rule_id: str, **fields) -> bool:
        if not fields:
            return False
        allowed = {
            "section_label", "title", "body", "category", "severity",
            "code_bad", "code_good", "source_pages", "order_index",
            "reviewed", "user_edited", "deleted",
        }
        sets = []
        params = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return False
        params.append(rule_id)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE rules SET {', '.join(sets)} WHERE rule_id = ?",
                params,
            )
            await db.commit()
        return cursor.rowcount > 0

    async def delete_rule(self, rule_id: str, soft: bool = True) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            if soft:
                cursor = await db.execute(
                    "UPDATE rules SET deleted = 1 WHERE rule_id = ?", (rule_id,)
                )
            else:
                cursor = await db.execute(
                    "DELETE FROM rules WHERE rule_id = ?", (rule_id,)
                )
            await db.commit()
        return cursor.rowcount > 0

    # --- helpers -------------------------------------------------------

    def _row_to_guide(self, row) -> GuideRecord:
        return GuideRecord(
            guide_id=row["guide_id"],
            name=row["name"],
            source_file=row["source_file"] or "",
            page_count=row["page_count"] or 0,
            status=row["status"] or "parsing",
            progress=row["progress"] or 0,
            error_msg=row["error_msg"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    # --- generated_qa --------------------------------------------------

    async def insert_qa(self, qa: GeneratedQARecord) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO generated_qa
                   (qa_id, rule_id, guide_id, qa_type, instruction, output,
                    status, user_edited, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    qa.qa_id, qa.rule_id, qa.guide_id, qa.qa_type,
                    qa.instruction, qa.output, qa.status, qa.user_edited,
                    qa.created_at,
                ),
            )
            await db.commit()
        return qa.qa_id

    async def list_qa(
        self,
        guide_id: str | None = None,
        rule_id: str | None = None,
        qa_type: str | None = None,
        status: str | None = None,
    ) -> list[GeneratedQARecord]:
        conditions = ["1=1"]
        params: list = []
        if guide_id:
            conditions.append("guide_id = ?")
            params.append(guide_id)
        if rule_id:
            conditions.append("rule_id = ?")
            params.append(rule_id)
        if qa_type:
            conditions.append("qa_type = ?")
            params.append(qa_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM generated_qa WHERE {where} ORDER BY created_at ASC",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_qa(r) for r in rows]

    async def get_qa(self, qa_id: str) -> GeneratedQARecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM generated_qa WHERE qa_id = ?", (qa_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return self._row_to_qa(row) if row else None

    async def update_qa(self, qa_id: str, **fields) -> bool:
        if not fields:
            return False
        allowed = {"instruction", "output", "qa_type", "status", "user_edited"}
        sets = []
        params = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return False
        params.append(qa_id)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE generated_qa SET {', '.join(sets)} WHERE qa_id = ?",
                params,
            )
            await db.commit()
        return cursor.rowcount > 0

    async def delete_qa(self, qa_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM generated_qa WHERE qa_id = ?", (qa_id,)
            )
            await db.commit()
        return cursor.rowcount > 0

    async def delete_qa_by_rule(self, rule_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM generated_qa WHERE rule_id = ?", (rule_id,)
            )
            await db.commit()
        return cursor.rowcount

    async def count_qa(self, guide_id: str, status: str | None = None) -> int:
        conditions = ["guide_id = ?"]
        params: list = [guide_id]
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = " AND ".join(conditions)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"SELECT COUNT(*) FROM generated_qa WHERE {where}", params
            ) as cursor:
                row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def list_approved_qa(self) -> list[GeneratedQARecord]:
        """모든 승인된 Q&A (export 통합용)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM generated_qa WHERE status = 'approved' ORDER BY created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_qa(r) for r in rows]

    # --- helpers -------------------------------------------------------

    def _row_to_qa(self, row) -> GeneratedQARecord:
        return GeneratedQARecord(
            qa_id=row["qa_id"],
            rule_id=row["rule_id"],
            guide_id=row["guide_id"],
            qa_type=row["qa_type"] or "code_review",
            instruction=row["instruction"] or "",
            output=row["output"] or "",
            status=row["status"] or "pending",
            user_edited=row["user_edited"] or 0,
            created_at=row["created_at"] or "",
        )

    def _row_to_rule(self, row) -> RuleRecord:
        return RuleRecord(
            rule_id=row["rule_id"],
            guide_id=row["guide_id"],
            section_label=row["section_label"] or "",
            title=row["title"] or "",
            body=row["body"] or "",
            category=row["category"] or "기타",
            severity=row["severity"] or "unknown",
            code_bad=row["code_bad"] or "",
            code_good=row["code_good"] or "",
            source_pages=row["source_pages"] or "",
            order_index=row["order_index"] or 0,
            reviewed=row["reviewed"] or 0,
            user_edited=row["user_edited"] or 0,
            deleted=row["deleted"] or 0,
            created_at=row["created_at"] or "",
        )
