from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class KnowledgeEntry:
    entry_id: str
    question: str
    answer: str
    source_chunks: list[str]
    score: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags: list[str] = field(default_factory=list)


class KnowledgeStore:
    """베스트 답변을 저장하고 FAQ를 생성합니다."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._file = self.storage_path / "knowledge.json"
        self._entries: list[KnowledgeEntry] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._entries = [KnowledgeEntry(**e) for e in data]

    def _save(self) -> None:
        data = [asdict(e) for e in self._entries]
        self._file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, entry: KnowledgeEntry) -> None:
        self._entries.append(entry)
        self._save()

    def generate_faq(self, top_n: int = 20) -> list[dict]:
        sorted_entries = sorted(self._entries, key=lambda e: e.score, reverse=True)
        return [
            {"question": e.question, "answer": e.answer, "score": e.score}
            for e in sorted_entries[:top_n]
        ]

    def search(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        q_words = set(query.lower().split())
        scored = []
        for entry in self._entries:
            e_words = set(entry.question.lower().split())
            overlap = len(q_words & e_words) / max(len(q_words), 1)
            if overlap > 0:
                scored.append((overlap, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]
