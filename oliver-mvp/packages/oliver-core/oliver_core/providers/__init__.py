"""
oliver_core.providers — provider-agnostic model access.

Public surface is the PORT and the factory only. Concrete providers (e.g. Ollama)
are intentionally not re-exported here: callers select via `get_provider()` and
depend on `LLMProvider`, so no caller is coupled to a vendor.
"""
from oliver_core.providers.base import (
    Completion,
    CompletionOptions,
    LLMProvider,
    Message,
    ProviderError,
)
from oliver_core.providers.factory import get_provider

__all__ = [
    "LLMProvider",
    "Message",
    "CompletionOptions",
    "Completion",
    "ProviderError",
    "get_provider",
]
