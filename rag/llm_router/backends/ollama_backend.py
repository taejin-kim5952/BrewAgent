from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .base import GenerateParams, LLMBackend


class OllamaBackend(LLMBackend):
    """Ollama HTTP API를 통한 로컬 LLM 백엔드."""

    def __init__(self, base_url: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self._model = model
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def _build_messages(self, prompt: str, system_prompt: str | None) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _messages_to_generate_prompt(messages: list[dict]) -> str:
        """구버전 /api/generate 호환용 단일 프롬프트."""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"### {role}:\n{content}")
        return "\n\n".join(parts).strip()

    def _options(self, params: GenerateParams) -> dict:
        return {
            "temperature": params.temperature,
            "num_predict": params.max_tokens,
            "top_p": params.top_p,
        }

    def _ollama_error_detail(self, resp: httpx.Response) -> str:
        """비스트리밍 응답용 (본문이 이미 로드된 경우)."""
        try:
            body = resp.json()
            if isinstance(body, dict) and "error" in body:
                return str(body["error"])
        except Exception:
            pass
        try:
            return (resp.text or "")[:800]
        except Exception:
            return f"HTTP {resp.status_code}"

    @staticmethod
    async def _ollama_error_detail_async(resp: httpx.Response) -> str:
        """스트리밍 응답은 .text 전에 aread() 필요 (ResponseNotRead 방지)."""
        try:
            await resp.aread()
        except Exception:
            pass
        try:
            body = resp.json()
            if isinstance(body, dict) and "error" in body:
                return str(body["error"])
        except Exception:
            pass
        try:
            return (resp.text or "")[:800]
        except Exception:
            return f"HTTP {resp.status_code}"

    async def generate(self, prompt: str, params: GenerateParams) -> str:
        messages = self._build_messages(prompt, params.system_prompt)
        opts = self._options(params)
        chat_payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": opts,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=chat_payload)
            if resp.status_code == 404:
                await resp.aclose()
                gen_payload = {
                    "model": self._model,
                    "prompt": self._messages_to_generate_prompt(messages),
                    "stream": False,
                    "options": opts,
                }
                resp = await client.post(f"{self.base_url}/api/generate", json=gen_payload)
            if not resp.is_success:
                detail = self._ollama_error_detail(resp)
                raise RuntimeError(
                    f"Ollama HTTP {resp.status_code} for {resp.request.url!s}: {detail}"
                ) from None
            data = resp.json()
            if "message" in data:
                return data["message"]["content"]
            return data.get("response", "")

    async def stream(self, prompt: str, params: GenerateParams) -> AsyncIterator[str]:
        messages = self._build_messages(prompt, params.system_prompt)
        opts = self._options(params)
        chat_payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": opts,
        }
        gen_payload = {
            "model": self._model,
            "prompt": self._messages_to_generate_prompt(messages),
            "stream": True,
            "options": opts,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            req = client.build_request("POST", f"{self.base_url}/api/chat", json=chat_payload)
            resp = await client.send(req, stream=True)
            try:
                if resp.status_code == 404:
                    await resp.aclose()
                    async with client.stream(
                        "POST", f"{self.base_url}/api/generate", json=gen_payload
                    ) as gen_resp:
                        if not gen_resp.is_success:
                            detail = await self._ollama_error_detail_async(gen_resp)
                            raise RuntimeError(
                                f"Ollama HTTP {gen_resp.status_code} for {gen_resp.request.url!s}: {detail}"
                            ) from None
                        async for line in gen_resp.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                    return

                if not resp.is_success:
                    detail = await self._ollama_error_detail_async(resp)
                    raise RuntimeError(
                        f"Ollama HTTP {resp.status_code} for {resp.request.url!s}: {detail}"
                    ) from None

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
            finally:
                await resp.aclose()
