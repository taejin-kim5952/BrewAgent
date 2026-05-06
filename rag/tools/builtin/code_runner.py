from __future__ import annotations

import asyncio
import sys

from ..registry import ToolDefinition


async def _code_runner_handler(code: str, timeout: int = 10) -> dict:
    """Python 코드를 격리된 subprocess에서 실행합니다."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": f"실행 시간 초과 ({timeout}초)"}

    return {
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "returncode": proc.returncode,
    }


def code_runner_tool() -> ToolDefinition:
    return ToolDefinition(
        name="code_runner",
        description="Python 코드를 실행하고 출력을 반환합니다.",
        parameters={
            "code": {"type": "string", "description": "실행할 Python 코드"},
            "timeout": {"type": "integer", "description": "최대 실행 시간(초)", "default": 10},
        },
        handler=_code_runner_handler,
    )
