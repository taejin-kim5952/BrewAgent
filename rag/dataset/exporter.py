from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .interaction_logger import InteractionRecord


@dataclass
class ExportResult:
    output_path: str
    record_count: int
    format: str


class JSONLExporter:
    """선택된 인터랙션을 파인튜닝용 JSONL로 내보냅니다."""

    def export_openai(self, records: list[InteractionRecord], output_path: Path) -> ExportResult:
        """OpenAI fine-tuning 형식: {"messages": [...]}"""
        with open(output_path, "w", encoding="utf-8") as f:
            for r in records:
                obj = {
                    "messages": [
                        {"role": "user", "content": r.query},
                        {"role": "assistant", "content": r.response},
                    ]
                }
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return ExportResult(output_path=str(output_path), record_count=len(records), format="openai")

    def export_alpaca(self, records: list[InteractionRecord], output_path: Path) -> ExportResult:
        """Alpaca 형식: {"instruction": ..., "input": "", "output": ...}"""
        with open(output_path, "w", encoding="utf-8") as f:
            for r in records:
                obj = {
                    "instruction": r.query,
                    "input": "",
                    "output": r.response,
                }
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return ExportResult(output_path=str(output_path), record_count=len(records), format="alpaca")

    def export_sharegpt(self, records: list[InteractionRecord], output_path: Path) -> ExportResult:
        """ShareGPT 형식: {"conversations": [...]}"""
        with open(output_path, "w", encoding="utf-8") as f:
            for r in records:
                obj = {
                    "conversations": [
                        {"from": "human", "value": r.query},
                        {"from": "gpt", "value": r.response},
                    ]
                }
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return ExportResult(output_path=str(output_path), record_count=len(records), format="sharegpt")
