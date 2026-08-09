"""Shared fixtures for the LLM-migration tests: provider stubs that satisfy the
LLMProvider port (no network, no vendor), and a representative submission."""
import pytest

from oliver_core.providers.base import Completion, ProviderError
from oliver_core.schemas import SubmissionCreate

VALID_JSON = (
    '{"value": 82, "confidence": 0.8, "summary": "Strong, quantified idea.", '
    '"evidence": [{"claim": "impact quantified", "excerpt": "2M EUR/year", "confidence": 0.9}], '
    '"gaps": ["baseline could be sharper"], "reasoning": "meets most weighted criteria"}'
)


class StubProvider:
    """Returns canned text for every completion. name/model are plain attributes —
    structurally sufficient for the runtime-checkable LLMProvider port."""
    name = "stub"
    model = "stub-model"

    def __init__(self, text: str = VALID_JSON):
        self._text = text

    async def complete(self, messages, *, options=None):
        return Completion(text=self._text, model=self.model, prompt_tokens=10, completion_tokens=5)


class FailingProvider:
    name = "failing"
    model = "none"

    async def complete(self, messages, *, options=None):
        raise ProviderError("simulated provider failure")


@pytest.fixture
def valid_provider():
    return StubProvider()


@pytest.fixture
def make_stub():
    """Factory for a stub returning custom text (bad JSON, invalid schema, etc.)."""
    return StubProvider


@pytest.fixture
def failing_provider():
    return FailingProvider()


@pytest.fixture
def strong_sub():
    return SubmissionCreate(
        title="Predictive maintenance for turbines",
        problem_statement=(
            "Unplanned turbine downtime costs about 2M EUR per year across the fleet. "
            "We want 48-hour advance failure warnings from vibration data."
        ),
        proposed_approach="Train an anomaly-detection model on historical vibration data.",
        expected_value="Avoid ~2M EUR/year in unplanned downtime.",
        data_sources="PI System vibration telemetry, maintenance logs.",
        sponsor="VP Gas Services",
        team_size=4,
    )
