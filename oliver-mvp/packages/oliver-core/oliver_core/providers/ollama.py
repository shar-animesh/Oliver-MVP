"""
Ollama provider — ONE implementation of the LLMProvider port.

This is the only module in Oliver that knows Ollama's wire protocol. It is
selected via the factory (OLIVER_LLM_PROVIDER=ollama) and is never imported by
business logic. Replacing it with Azure OpenAI / Foundry means adding a sibling
adapter and a factory branch — nothing else changes.

The HTTP call is behind an injected `AsyncJSONTransport` so the adapter is unit
-testable without a running Ollama daemon and without making httpx a hard
dependency of oliver-core (httpx is imported lazily by the default transport).
"""
from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

from oliver_core.providers.base import (
    Completion,
    CompletionOptions,
    Message,
    ProviderError,
)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"
DEFAULT_TIMEOUT = 120.0


@runtime_checkable
class AsyncJSONTransport(Protocol):
    """Minimal async HTTP-JSON seam. Injected in tests; the default is httpx."""

    async def post_json(self, url: str, payload: dict, *, timeout: float) -> dict:
        ...


class _HttpxTransport:
    """Default transport. httpx is imported lazily so importing this module (or
    the factory) does not require httpx unless a real call is made."""

    async def post_json(self, url: str, payload: dict, *, timeout: float) -> dict:
        try:
            import httpx  # lazy: not a hard dependency of oliver-core
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise ProviderError(
                "httpx is required to call Ollama at runtime "
                "(`pip install httpx`); tests inject a transport instead."
            ) from exc
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()


class OllamaProvider:
    """LLMProvider backed by a local/remote Ollama server."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[AsyncJSONTransport] = None,
    ) -> None:
        self._base_url = (
            base_url or os.getenv("OLIVER_OLLAMA_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._model = model or os.getenv("OLIVER_OLLAMA_MODEL") or DEFAULT_MODEL
        self._timeout = timeout
        self._transport: AsyncJSONTransport = transport or _HttpxTransport()

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[Message],
        *,
        options: Optional[CompletionOptions] = None,
    ) -> Completion:
        options = options or CompletionOptions()
        gen: dict = {"temperature": options.temperature}
        if options.max_tokens is not None:
            gen["num_predict"] = options.max_tokens

        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": gen,
        }
        if options.json_mode:
            payload["format"] = "json"      # Ollama structured-output flag

        try:
            data = await self._transport.post_json(
                f"{self._base_url}/api/chat", payload, timeout=self._timeout
            )
        except ProviderError:
            raise
        except Exception as exc:  # transport/HTTP errors -> uniform ProviderError
            raise ProviderError(f"Ollama call failed: {exc}") from exc

        text = (data.get("message") or {}).get("content", "")
        return Completion(
            text=text,
            model=data.get("model", self._model),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )
