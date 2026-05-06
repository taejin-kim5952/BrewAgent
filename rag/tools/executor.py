from __future__ import annotations

from typing import Any

from .registry import ToolRegistry


class ToolExecutor:
    """도구를 안전하게 실행합니다."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        if tool is None:
            return {"error": f"도구를 찾을 수 없습니다: {tool_name}"}

        try:
            result = await tool.handler(**arguments)
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}
