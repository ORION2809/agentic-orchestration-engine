"""Instructor integration for structured Pydantic output from LLMs."""

from __future__ import annotations

import os
from typing import Any, TypeVar

import instructor
import litellm
import structlog

from app.llm.token_tracker import TokenTracker
from app.llm.model_selector import AdaptiveModelSelector
from app.models.errors import LLMParseError
from app.observability.metrics import METRICS

logger = structlog.get_logger()

T = TypeVar("T")

# Suppress litellm
litellm.set_verbose = False


class StructuredLLM:
    """Forces LLM to return validated Pydantic models via instructor.

    Uses instructor.from_litellm() for provider-agnostic structured output.
    """

    def __init__(
        self,
        model: str | None = None,
        tracker: TokenTracker | None = None,
        model_selector: AdaptiveModelSelector | None = None,
    ):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        self.tracker = tracker or TokenTracker()
        self.model_selector = model_selector
        self.client = instructor.from_litellm(litellm.completion)

    def create(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        phase: str,
        model_override: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> T:
        """Call LLM and return a validated Pydantic model.

        Args:
            messages: Chat messages list.
            response_model: Pydantic model class to validate against.
            phase: Agent phase name for tracking.
            model_override: Override the default model.
            temperature: Sampling temperature.
            max_retries: Instructor retry count on parse failure.
            **kwargs: Additional litellm kwargs.

        Returns:
            An instance of response_model.

        Raises:
            LLMParseError: If output cannot be parsed after retries.
        """
        if model_override:
            model = model_override
        elif self.model_selector:
            model = self.model_selector.get_model(phase)
        else:
            model = self.model

        try:
            METRICS.llm_calls.inc(phase=phase)
            result = self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_model=response_model,
                max_retries=max_retries,
                temperature=temperature,
                **kwargs,
            )

            # instructor wraps litellm — track tokens from the raw response
            # The usage is attached to the completion result by instructor
            if hasattr(result, "_raw_response"):
                usage = getattr(result._raw_response, "usage", None)
                self.tracker.record(phase, model, usage)
                if usage and hasattr(usage, "total_tokens"):
                    METRICS.llm_tokens.inc(amount=usage.total_tokens, phase=phase)
            else:
                # Estimate: model name + rough count
                self.tracker.record(phase, model, {"total_tokens": 0})

            logger.debug(
                "structured_output_success",
                phase=phase,
                model=model,
                response_model=response_model.__name__,
            )
            return result

        except Exception as e:
            METRICS.llm_errors.inc(phase=phase)
            logger.error(
                "structured_output_failed",
                phase=phase,
                model=model,
                error=str(e),
            )
            raise LLMParseError(
                f"Failed to parse structured output for {response_model.__name__}: {e}"
            ) from e
