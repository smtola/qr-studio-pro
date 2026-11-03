"""Minimal Claude Messages API client over HTTPS (no SDK needed). The transport is injectable for tests."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Callable

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AIError(RuntimeError):
    """User-facing AI failure (never contains the API key)."""


def _ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def _urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIError("Could not reach Claude. Check your internet connection and try again.") from e


class ClaudeClient:
    def __init__(self, api_key: str, model: str, transport: Callable | None = None, timeout: float = 120):
        self.api_key, self.model, self.timeout = api_key.strip(), model, timeout
        self.transport = transport or _urllib_transport

    def create(self, messages: list[dict], *, system: str = "", tools: list[dict] | None = None, max_tokens: int = 2048) -> dict:
        if not self.api_key:
            raise AIError("Add your Claude API key first (the Settings button).")
        payload: dict = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        headers = {"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": API_VERSION}
        status, raw = self.transport(API_URL, headers, json.dumps(payload).encode("utf-8"), self.timeout)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            data = {}
        if status == 200 and isinstance(data, dict) and "content" in data:
            return data
        raise AIError(_explain(status, data))


def _explain(status: int, data: dict) -> str:
    err = data.get("error", {}) if isinstance(data, dict) else {}
    detail = str(err.get("message", ""))
    if status == 401:
        return "Claude rejected the API key. Check it in Settings."
    if status == 403:
        return "This API key is not allowed to use that model or feature."
    if status == 404:
        return "That model name was not found. Choose another model in Settings."
    if status == 429:
        return "Claude is limiting requests right now (rate limit or usage limit). Wait a moment and try again."
    if status in (500, 502, 503, 504, 529):
        return "Claude is busy or temporarily unavailable. Try again in a minute."
    if status == 400 and "credit" in detail.lower():
        return "Your Anthropic account has no credit left. Add credit in the Anthropic Console."
    return f"Claude returned an error ({status}). {detail[:200]}".strip()
