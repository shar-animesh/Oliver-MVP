"""
Provider selection — the single place that maps configuration to a concrete
LLMProvider. Business logic depends on this factory and the `LLMProvider` port,
never on a concrete provider module.

Selection is by `OLIVER_LLM_PROVIDER`:
  - unset / "none" / "disabled" -> None  (no provider configured; callers fall
    back to the deterministic path — that fallback lands in the next increment)
  - "ollama"                    -> OllamaProvider (temporary development provider)
  - "azure_openai" / "foundry"  -> added in a later increment (a new adapter
                                    module + a branch here; no caller changes)

Concrete providers are imported lazily inside their branch so that importing this
module pulls in no vendor SDK / HTTP client until a provider is actually chosen.
"""
from __future__ import annotations

import os
from typing import Optional

from oliver_core.providers.base import LLMProvider

_DISABLED = {"", "none", "disabled", "off"}


def get_provider(name: Optional[str] = None) -> Optional[LLMProvider]:
    """Return the configured provider, or None when none is configured.

    `name` overrides the environment (useful for tests and explicit wiring).
    """
    selected = (name if name is not None else os.getenv("OLIVER_LLM_PROVIDER", "none"))
    selected = selected.strip().lower()

    if selected in _DISABLED:
        return None

    if selected == "ollama":
        from oliver_core.providers.ollama import OllamaProvider
        return OllamaProvider()

    raise ValueError(
        f"unknown LLM provider '{selected}'. "
        f"Supported now: none, ollama. "
        f"(azure_openai / foundry are added in a later increment.)"
    )
