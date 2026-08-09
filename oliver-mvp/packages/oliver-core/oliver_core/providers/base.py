"""
Provider-agnostic LLM port.

This is the ONLY contract the rest of Oliver (agents, coordinator, narrator,
future Registrar) is allowed to depend on for model access. Concrete providers
implement `LLMProvider` and are selected at runtime by the factory. No
business-logic module imports a concrete provider, and nothing outside a provider
module knows which vendor is in use — this port names no vendor by design.

Design intent (doc 02 — "change the plumbing, not the assessment logic"):
  - `complete()` covers the "model call" role of an agent (prompt -> completion).
    Cloud chat-completion APIs and local model servers both map onto it directly.
  - Higher-order agent orchestration (e.g. Foundry Agent Service threads/tools) is
    a separate seam at the agent-runtime layer, not this model-provider port; kept
    distinct on purpose so this abstraction stays honest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    """A single chat message. Roles: 'system' | 'user' | 'assistant'."""
    role: str
    content: str


@dataclass(frozen=True)
class CompletionOptions:
    """Vendor-neutral generation options. Providers map these onto their own
    parameters and ignore any they do not support (documented per provider)."""
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    json_mode: bool = False          # request structured/JSON output where supported


@dataclass(frozen=True)
class Completion:
    """A vendor-neutral completion result. Token counts are optional because not
    every provider reports them."""
    text: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


@runtime_checkable
class LLMProvider(Protocol):
    """The port. Any provider that satisfies this can be dropped in with no change
    to callers. `runtime_checkable` so tests can assert conformance structurally."""

    @property
    def name(self) -> str:
        """Stable identifier for logs/telemetry, set by each concrete provider."""
        ...

    @property
    def model(self) -> str:
        """The configured model / deployment id, for provenance. Vendor-neutral:
        callers read it without knowing which provider is in use."""
        ...

    async def complete(
        self,
        messages: list[Message],
        *,
        options: Optional[CompletionOptions] = None,
    ) -> Completion:
        """Produce a completion for the given chat messages."""
        ...


class ProviderError(RuntimeError):
    """Raised by a provider when a model call fails. Callers (a future coordinator)
    translate this into per-dimension fallback; agents never see vendor errors."""
