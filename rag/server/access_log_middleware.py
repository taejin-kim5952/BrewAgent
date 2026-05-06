"""HTTP 요청/응답 요약 로깅 (스트리밍 응답도 상태코드만 캡처)."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# JSON 로그에 마스킹할 키 (이 문자열이 키에 포함되면 마스킹)
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in _SENSITIVE_KEY_FRAGMENTS)


def _mask_json(obj: Any, depth: int = 0) -> Any:
    if depth > 32:
        return "<max depth>"
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if _is_sensitive_key(str(k)):
                out[str(k)] = "***"
            else:
                out[str(k)] = _mask_json(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_mask_json(v, depth + 1) for v in obj[:200]]
    return obj


def _safe_request_body_preview(raw: bytes, max_chars: int = 8000) -> str:
    if not raw:
        return ""
    if len(raw) > max_chars:
        raw = raw[:max_chars]
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
        return json.dumps(_mask_json(data), ensure_ascii=False)
    except json.JSONDecodeError:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)


def _header(scope: Scope, name: bytes) -> bytes:
    for k, v in scope.get("headers") or []:
        if k.lower() == name.lower():
            return v
    return b""


def _should_skip_path(path: str) -> bool:
    if path == "/health":
        return True
    if path in ("/docs", "/redoc", "/openapi.json", "/favicon.ico"):
        return True
    if path.startswith("/docs/") or path.startswith("/redoc/"):
        return True
    if path.startswith("/ui/"):
        return True
    return False


def _should_capture_body_for_log(scope: Scope) -> bool:
    method = scope.get("method", "GET")
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    ct = _header(scope, b"content-type")
    if ct.startswith(b"multipart/"):
        return False
    cl = _header(scope, b"content-length")
    if cl.isdigit() and int(cl) > 512 * 1024:
        return False
    return True


class AccessLogMiddleware:
    """경로·쿼리·(선택) 마스킹 요청 본문, 응답 상태코드 로깅."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        qs = scope.get("query_string", b"") or b""
        qs_s = qs.decode("utf-8", errors="replace") if qs else ""

        if _should_skip_path(path):
            await self.app(scope, receive, send)
            return

        status_code = 0

        async def logging_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 0))
            await send(message)

        if not _should_capture_body_for_log(scope):
            await self.app(scope, receive, logging_send)
            extra = ""
            if method not in ("GET", "HEAD", "OPTIONS"):
                ct = _header(scope, b"content-type").decode("utf-8", errors="replace")
                cl = _header(scope, b"content-length").decode("utf-8", errors="replace")
                extra = f" content-type={ct!r} content-length={cl!r}"
            logger.info(
                "HTTP {} {}{} → {}{}",
                method,
                path,
                f"?{qs_s}" if qs_s else "",
                status_code or "?",
                extra,
            )
            return

        messages: list[Message] = []
        body_total = 0
        while True:
            msg = await receive()
            messages.append(msg)
            if msg["type"] == "http.disconnect":
                break
            if msg["type"] == "http.request":
                body_total += len(msg.get("body", b""))
                if not msg.get("more_body", False):
                    break

        idx = 0

        async def replay_receive() -> Message:
            nonlocal idx
            if idx < len(messages):
                m = messages[idx]
                idx += 1
                return m
            return await receive()

        raw = b""
        for m in messages:
            if m["type"] == "http.request":
                raw += m.get("body", b"")
        if body_total > 512 * 1024:
            logger.info(
                "HTTP {} {}{} body=<omitted {} bytes>",
                method,
                path,
                f"?{qs_s}" if qs_s else "",
                body_total,
            )
        else:
            preview = _safe_request_body_preview(raw) if raw else ""
            if preview:
                logger.info(
                    "HTTP {} {}{} body={}",
                    method,
                    path,
                    f"?{qs_s}" if qs_s else "",
                    preview,
                )
            else:
                logger.info(
                    "HTTP {} {}{}",
                    method,
                    path,
                    f"?{qs_s}" if qs_s else "",
                )

        await self.app(scope, replay_receive, logging_send)
        logger.info("HTTP {} {} → {}", method, path, status_code or "?")
