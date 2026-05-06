from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


class ToolRegistry:
    """사용 가능한 도구를 등록하고 조회합니다."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]


def default_registry() -> ToolRegistry:
    from .builtin.db_query import db_query_tool
    from .builtin.code_runner import code_runner_tool

    registry = ToolRegistry()
    registry.register(db_query_tool())
    registry.register(code_runner_tool())
    return registry
