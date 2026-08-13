"""Pydantic-backed tool schemas exposed to the Oliver model."""

from typing import List, Union

from openai import pydantic_function_tool
from openai.types.chat import ChatCompletionFunctionToolParam
from openai.types.responses import WebSearchToolParam
from pydantic import BaseModel, ConfigDict, Field

SEARCH_RELATED_IDEAS_TOOL_NAME = "search_related_ideas"


class SearchRelatedIdeasInput(BaseModel):
    """Input for semantic search across participant-authored Oliver conversations."""

    query: str = Field(
        min_length=3,
        description=(
            "A standalone semantic search query describing the initiative's problem, intended users, proposed capability, "
            "important business context, and relevant technologies."
        ),
    )

    model_config = ConfigDict(extra="forbid")


AZURE_WEB_SEARCH_TOOL: WebSearchToolParam = {"type": "web_search"}

SEARCH_RELATED_IDEAS_TOOL: ChatCompletionFunctionToolParam = pydantic_function_tool(
    SearchRelatedIdeasInput,
    name=SEARCH_RELATED_IDEAS_TOOL_NAME,
    description=(
        "Search participant-authored Oliver email conversations for semantically related internal AI initiatives. "
        "Use a complete, standalone query containing enough context to match related problems, capabilities, users, and technologies. "
        "Use this when an initiative assessment or coordination reply could benefit from similar work or relevant contacts."
    ),
)

ToolSchema = Union[WebSearchToolParam, ChatCompletionFunctionToolParam]

TOOL_SCHEMAS: List[ToolSchema] = [
    AZURE_WEB_SEARCH_TOOL,
    SEARCH_RELATED_IDEAS_TOOL,
]
