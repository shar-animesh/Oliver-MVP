"""
Provider abstraction.

Proves: the port is provider-agnostic, the factory is the single selection point,
the Ollama adapter speaks Ollama correctly (via an injected transport, no daemon),
a different provider drops in with no consumer change, and no business-logic import
drags the Ollama module (isolation).
"""
import asyncio
import subprocess
import sys

import pytest

from oliver_core.providers import (
    Completion,
    CompletionOptions,
    LLMProvider,
    Message,
    get_provider,
)
from oliver_core.providers.ollama import OllamaProvider


# ── Factory selection ─────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "none", "disabled", "off", ""])
def test_factory_returns_none_when_unconfigured(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("OLIVER_LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("OLIVER_LLM_PROVIDER", value)
    assert get_provider() is None


def test_factory_selects_ollama(monkeypatch):
    monkeypatch.setenv("OLIVER_LLM_PROVIDER", "ollama")
    p = get_provider()
    assert isinstance(p, OllamaProvider)
    assert p.name == "ollama"


def test_factory_rejects_unknown(monkeypatch):
    monkeypatch.setenv("OLIVER_LLM_PROVIDER", "does-not-exist")
    with pytest.raises(ValueError):
        get_provider()


def test_explicit_name_overrides_env(monkeypatch):
    monkeypatch.setenv("OLIVER_LLM_PROVIDER", "ollama")
    assert get_provider("none") is None


# ── Ollama adapter (no daemon — transport injected) ───────────────────────

class _FakeTransport:
    def __init__(self, response):
        self.response = response
        self.last_url = None
        self.last_payload = None

    async def post_json(self, url, payload, *, timeout):
        self.last_url = url
        self.last_payload = payload
        return self.response


def test_ollama_builds_request_and_parses_response():
    fake = _FakeTransport({
        "model": "llama3.1",
        "message": {"role": "assistant", "content": "hello world"},
        "prompt_eval_count": 11,
        "eval_count": 3,
    })
    provider = OllamaProvider(model="llama3.1", transport=fake)
    out = asyncio.run(provider.complete(
        [Message(role="system", content="be terse"), Message(role="user", content="hi")],
        options=CompletionOptions(temperature=0.1, max_tokens=64, json_mode=True),
    ))

    # request shaped for Ollama /api/chat
    assert fake.last_url.endswith("/api/chat")
    assert fake.last_payload["model"] == "llama3.1"
    assert fake.last_payload["stream"] is False
    assert fake.last_payload["messages"][0] == {"role": "system", "content": "be terse"}
    assert fake.last_payload["options"]["temperature"] == 0.1
    assert fake.last_payload["options"]["num_predict"] == 64
    assert fake.last_payload["format"] == "json"

    # response parsed into the vendor-neutral Completion
    assert isinstance(out, Completion)
    assert out.text == "hello world"
    assert out.model == "llama3.1"
    assert out.prompt_tokens == 11 and out.completion_tokens == 3


def test_ollama_conforms_to_port():
    assert isinstance(OllamaProvider(transport=_FakeTransport({})), LLMProvider)


# ── Provider-agnosticism: a different provider, same consumer path ─────────

class _StubAzure:
    """Stands in for a future Azure OpenAI adapter — satisfies the port only."""
    @property
    def name(self) -> str:
        return "azure_openai"

    @property
    def model(self) -> str:
        return "gpt-4o"

    async def complete(self, messages, *, options=None):
        return Completion(text="from azure", model="gpt-4o")


async def _consume(provider: LLMProvider) -> str:
    """A consumer that knows only the port — no vendor specifics."""
    result = await provider.complete([Message(role="user", content="ping")])
    return f"{provider.name}:{result.text}"


def test_same_consumer_works_across_providers():
    ollama = OllamaProvider(transport=_FakeTransport(
        {"message": {"content": "from ollama"}, "model": "llama3.1"}))
    assert asyncio.run(_consume(ollama)) == "ollama:from ollama"
    assert asyncio.run(_consume(_StubAzure())) == "azure_openai:from azure"
    assert isinstance(_StubAzure(), LLMProvider)   # future adapter conforms structurally


# ── Isolation: nothing outside a provider module knows Ollama exists ──────

def _imports_ollama(import_stmt: str) -> bool:
    """True if running `import_stmt` in a fresh interpreter loads the Ollama module."""
    code = (
        f"import sys; {import_stmt}; "
        f"sys.exit(1 if 'oliver_core.providers.ollama' in sys.modules else 0)"
    )
    return subprocess.run([sys.executable, "-c", code]).returncode == 1


def test_business_logic_import_does_not_load_ollama():
    # Importing the core / assessor must not drag in the Ollama adapter.
    assert not _imports_ollama("import oliver_core; import oliver_core.mock_assessor")


def test_factory_import_does_not_load_ollama():
    # Even importing the factory must not load Ollama until a provider is chosen.
    assert not _imports_ollama("import oliver_core.providers.factory")
