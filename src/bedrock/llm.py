"""Minimal Groq chat client (OpenAI-compatible Chat Completions with tool calling), httpx only.

Groq's free tier has tight per-minute token budgets, so this client honours Retry-After on 429
and surfaces a clear error instead of hanging. Docs: https://console.groq.com/docs/tool-use
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    """Raised when the model cannot be reached or keeps failing; callers fall back gracefully."""


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set (put it in bedrock/.env; free keys: https://console.groq.com/keys)")
        self.model, self.max_retries, self._sleep = model, max_retries, sleep
        self._http = httpx.Client(
            timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def chat(self, messages: list[dict], tools: list[dict] | None = None, *, max_tokens: int = 2000,
             temperature: float = 0.1) -> dict:
        """One chat turn. Returns the assistant message dict (may contain tool_calls)."""
        body: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # these models spend max_tokens on hidden reasoning; keep it short
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                r = self._http.post(URL, json=body)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise LLMError(f"network error talking to Groq: {type(exc).__name__}") from exc
                self._sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    raise LLMError(f"Groq is rate-limiting or unavailable (HTTP {r.status_code}); try again shortly")
                try:
                    wait = float(r.headers.get("retry-after", delay))
                except ValueError:
                    wait = delay
                self._sleep(min(wait, 30))
                delay = min(delay * 2, 30)
                continue
            if r.status_code == 401:
                raise LLMError("Groq rejected the API key (HTTP 401)")
            if r.status_code == 400 and "tool_use_failed" in r.text:
                if attempt == self.max_retries:
                    raise LLMError("the model produced a malformed tool call repeatedly")
                body["temperature"] = 0.0  # a stricter retry usually fixes malformed tool JSON
                continue
            if r.status_code >= 400:
                raise LLMError(f"Groq error HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            u = data.get("usage") or {}
            self.usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            self.usage["completion_tokens"] += u.get("completion_tokens", 0)
            self.usage["calls"] += 1
            choice = data["choices"][0]
            return {**choice["message"], "_finish_reason": choice.get("finish_reason")}
        raise LLMError("no response from Groq")
