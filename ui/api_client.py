"""FastAPI 백엔드 호출 헬퍼.

Streamlit 페이지에서 import 해서 사용:
    from api_client import get, post, patch, delete

기본 베이스 URL: http://localhost:8000
환경변수 RAG_API_BASE 로 오버라이드 가능.
"""
from __future__ import annotations

import os
from typing import Any

import requests

API_BASE = os.environ.get("RAG_API_BASE", "http://localhost:8000")
DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 600  # 요약, Q&A 생성 등 LLM 호출용


class APIError(Exception):
    """API 호출 실패."""
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {detail}")


def _check(response: requests.Response) -> dict | list:
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text or f"HTTP {response.status_code}"
        raise APIError(response.status_code, detail)
    if not response.content:
        return {}
    return response.json()


def get(path: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    return _check(requests.get(API_BASE + path, params=params, timeout=timeout))


def post(
    path: str,
    json: dict | None = None,
    files: dict | None = None,
    data: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    return _check(requests.post(
        API_BASE + path, json=json, files=files, data=data, timeout=timeout,
    ))


def patch(path: str, json: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    return _check(requests.patch(API_BASE + path, json=json, timeout=timeout))


def delete(path: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    return _check(requests.delete(API_BASE + path, timeout=timeout))


def is_backend_alive() -> tuple[bool, str]:
    """백엔드 헬스 체크. (성공 여부, 메시지) 반환."""
    try:
        r = requests.get(API_BASE + "/health", timeout=3)
        if r.ok:
            data = r.json()
            return True, f"✅ 백엔드 정상 (storage: {data.get('storage', '?')})"
        return False, f"⚠️ HTTP {r.status_code}"
    except requests.ConnectionError:
        return False, "❌ 백엔드 연결 실패 (서버 미실행?)"
    except Exception as e:
        return False, f"❌ 오류: {e}"


def download_file(path: str, save_path: str, timeout: int = LONG_TIMEOUT) -> None:
    """파일 다운로드 (JSONL 등)."""
    r = requests.get(API_BASE + path, timeout=timeout, stream=True)
    if not r.ok:
        raise APIError(r.status_code, r.text)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def get_bytes(path: str, timeout: int = LONG_TIMEOUT) -> bytes:
    """파일 바이트 그대로 받기 (Streamlit download_button 용)."""
    r = requests.get(API_BASE + path, timeout=timeout)
    if not r.ok:
        raise APIError(r.status_code, r.text)
    return r.content
