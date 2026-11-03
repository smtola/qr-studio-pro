"""Minimal Groq chat client (OpenAI-compatible API) over HTTPS, no SDK needed. The transport is injectable for tests."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Callable

API_URL = "https://api.groq.com/openai/v1/chat/completions"


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
        raise AIError("Could not reach Groq. Check your internet connection and try again.") from e


class GroqClient:
    def __init__(self, api_key: str, model: str, transport: Callable | None = None, timeout: float = 120):
        self.api_key, self.model, self.timeout = api_key.strip(), model, timeout
        self.transport = transport or _urllib_transport

    def create(self, messages: list[dict], *, system: str = "", tools: list[dict] | None = None, max_tokens: int = 2048) -> dict:
        """Returns {"message": {...assistant message...}, "finish_reason": str}. `messages` excludes the system prompt."""
        if not self.api_key:
            raise AIError("Add your Groq API key first (the Settings button).")
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        payload: dict = {"model": self.model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.2}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"content-type": "application/json", "authorization": f"Bearer {self.api_key}",
                   "user-agent": "TLStudioPro"}
        status, raw = self.transport(API_URL, headers, json.dumps(payload).encode("utf-8"), self.timeout)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            data = {}
        if status == 200 and isinstance(data, dict) and data.get("choices"):
            ch = data["choices"][0]
            return {"message": ch.get("message") or {}, "finish_reason": ch.get("finish_reason") or ""}
        raise AIError(_explain(status, data))


def _explain(status: int, data: dict) -> str:
    err = data.get("error", {}) if isinstance(data, dict) else {}
    detail = str(err.get("message", "")) if isinstance(err, dict) else ""
    code = str(err.get("code", "")) if isinstance(err, dict) else ""
    if status == 401:
        return "Groq rejected the API key. Check it in Settings."
    if status == 403:
        return "This API key is not allowed to use that model or feature."
    if status == 404 or "model_not_found" in code or "does not exist" in detail:
        return "That model name was not found. Choose another model in Settings."
    if status == 429:
        return "Groq is limiting requests right now (rate limit or daily limit). Wait a moment and try again."
    if status in (500, 502, 503, 504):
        return "Groq is busy or temporarily unavailable. Try again in a minute."
    if "tool_use_failed" in code or "tool" in detail.lower() and status == 400:
        return "The model could not use the tool correctly. Try rephrasing, or choose a different model in Settings."
    return f"Groq returned an error ({status}). {detail[:200]}".strip()
