"""Prompt architecture — prompts are built from the deterministic rubric."""
from oliver_core.prompts import (
    DIMENSION_RUBRICS,
    PROMPT_VERSION,
    build_messages,
)
from oliver_core.mock_assessor import DIMENSION_KEYS
from oliver_core.providers.base import Message


def test_prompt_version_present():
    assert PROMPT_VERSION.startswith("assess-prompt/")


def test_rubric_covers_all_dimensions_and_weights_sum_100():
    assert set(DIMENSION_RUBRICS) == set(DIMENSION_KEYS)
    for dim, rubric in DIMENSION_RUBRICS.items():
        assert sum(c.weight for c in rubric.criteria) == 100, dim


def test_build_messages_shape_and_content(strong_sub):
    for dim in DIMENSION_KEYS:
        msgs = build_messages(dim, strong_sub)
        assert len(msgs) == 2
        assert all(isinstance(m, Message) for m in msgs)
        assert msgs[0].role == "system" and msgs[1].role == "user"
        # the rubric criteria appear in the user message (prompt derives from rubric)
        for c in DIMENSION_RUBRICS[dim].criteria:
            assert c.id in msgs[1].content
        # submission content is included
        assert "turbine" in msgs[1].content.lower()
        # JSON-only instruction present
        assert "JSON" in msgs[0].content


def test_empty_submission_still_builds(strong_sub):
    from oliver_core.schemas import SubmissionCreate
    sparse = SubmissionCreate(title="Bare idea", problem_statement="Something is slow.")
    msgs = build_messages("ideaCompleteness", sparse)
    assert "no fields provided" not in msgs[1].content  # title/problem present
