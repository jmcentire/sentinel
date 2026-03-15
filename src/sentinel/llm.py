"""Standalone LLM client for Sentinel — structured extraction via Anthropic API."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel

from sentinel.config import LLMConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Approximate cost per token (Claude Sonnet)
_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000


class LLMClient:
    """Anthropic API wrapper with structured extraction and budget tracking."""

    def __init__(self, config: LLMConfig) -> None:
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._budget_cap = config.budget_per_fix
        self._spend: float = 0.0
        self._client = None

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic()
            except ImportError:
                raise RuntimeError(
                    "anthropic package required for LLM features. "
                    "Install with: pip install sentinel-monitor[llm]"
                )
        return self._client

    @property
    def spend(self) -> float:
        return self._spend

    def is_budget_exceeded(self) -> bool:
        return self._spend >= self._budget_cap

    async def assess(
        self,
        schema: type[T],
        prompt: str,
        system: str,
        max_tokens: int | None = None,
    ) -> tuple[T, int, int]:
        """Structured extraction via tool_use. Returns (parsed_result, input_tokens, output_tokens)."""
        if self.is_budget_exceeded():
            raise BudgetExceededError(
                f"Budget exceeded: ${self._spend:.2f} >= ${self._budget_cap:.2f}"
            )

        client = self._get_client()
        tool_schema = _pydantic_to_tool_schema(schema)
        tokens = max_tokens or self._max_tokens

        response = await client.messages.create(
            model=self._model,
            max_tokens=tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
        )

        # Extract tool use result
        tool_result = None
        for block in response.content:
            if block.type == "tool_use":
                tool_result = block.input
                break

        if tool_result is None:
            raise LLMError("No tool_use block in response")

        # Parse into schema
        result = schema.model_validate(tool_result)

        # Track spending
        in_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens
        cost = (in_tokens * _COST_PER_INPUT_TOKEN) + (out_tokens * _COST_PER_OUTPUT_TOKEN)
        self._spend += cost

        return result, in_tokens, out_tokens

    async def generate(
        self,
        prompt: str,
        system: str,
        max_tokens: int | None = None,
    ) -> str:
        """Unstructured text generation. Returns raw text response."""
        if self.is_budget_exceeded():
            raise BudgetExceededError(
                f"Budget exceeded: ${self._spend:.2f} >= ${self._budget_cap:.2f}"
            )

        client = self._get_client()
        tokens = max_tokens or self._max_tokens

        response = await client.messages.create(
            model=self._model,
            max_tokens=tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        in_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens
        cost = (in_tokens * _COST_PER_INPUT_TOKEN) + (out_tokens * _COST_PER_OUTPUT_TOKEN)
        self._spend += cost

        return text

    async def close(self) -> None:
        """Clean up the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None


class LLMError(Exception):
    """LLM call failed."""


class BudgetExceededError(LLMError):
    """Per-fix budget exceeded."""


def _pydantic_to_tool_schema(schema: type[BaseModel]) -> dict:
    """Convert a pydantic model to an Anthropic tool schema."""
    json_schema = schema.model_json_schema()

    # Remove title/description from top level to avoid duplication
    properties = json_schema.get("properties", {})
    required = json_schema.get("required", [])

    return {
        "name": schema.__name__,
        "description": schema.__doc__ or f"Extract {schema.__name__}",
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
