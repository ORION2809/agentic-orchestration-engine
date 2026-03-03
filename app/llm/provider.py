"""LLM provider abstraction — hot-swappable via env var, with fallback chain and circuit breakers."""

from __future__ import annotations

import os
from typing import Any

import litellm
import structlog

from app.llm.circuit_breaker import SlidingWindowCircuitBreaker
from app.llm.model_selector import AdaptiveModelSelector
from app.llm.token_tracker import TokenTracker
from app.models.errors import CircuitBreakerOpenError, LLMProviderError
from app.observability.metrics import METRICS

logger = structlog.get_logger()

# Suppress litellm's verbose logging
litellm.set_verbose = False


def _detect_provider(model: str) -> str:
    """Heuristic to detect the provider from a model name."""
    model_lower = model.lower()
    if "claude" in model_lower or "anthropic" in model_lower:
        return "anthropic"
    if "gemini" in model_lower or "google" in model_lower:
        return "google"
    if "ollama" in model_lower:
        return "ollama"
    return "openai"


class LLMProvider:
    """Hot-swappable LLM backend via env var LLM_MODEL.

    Features:
        - Automatic fallback chain across providers
        - Per-provider sliding-window circuit breakers
        - Token tracking per phase
        - Adaptive model selection via AdaptiveModelSelector
    """

    def __init__(
        self,
        model: str | None = None,
        fallback_models: list[str] | None = None,
        tracker: TokenTracker | None = None,
        model_selector: AdaptiveModelSelector | None = None,
    ):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        self.fallback_models = fallback_models or [
            m.strip()
            for m in os.getenv("LLM_FALLBACK", "").split(",")
            if m.strip()
        ]
        self.tracker = tracker or TokenTracker()
        self.model_selector = model_selector

        # One breaker per provider
        self.breakers: dict[str, SlidingWindowCircuitBreaker] = {}

    def _get_breaker(self, provider: str) -> SlidingWindowCircuitBreaker:
        if provider not in self.breakers:
            self.breakers[provider] = SlidingWindowCircuitBreaker(provider)
        return self.breakers[provider]

    def complete(
        self,
        messages: list[dict[str, str]],
        phase: str,
        model_override: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Call LLM with automatic fallback and token tracking.

        Args:
            messages: Chat messages list.
            phase: Agent phase name for tracking.
            model_override: Override the default model for this call.
            **kwargs: Additional arguments passed to litellm.completion.

        Returns:
            The LLM response content string.

        Raises:
            LLMProviderError: If all models in the chain fail.
        """
        # Determine primary model
        if model_override:
            primary = model_override
        elif self.model_selector:
            primary = self.model_selector.get_model(phase)
        else:
            primary = self.model

        models_to_try = [primary] + [m for m in self.fallback_models if m != primary]
        last_error: Exception | None = None

        for model in models_to_try:
            provider = _detect_provider(model)
            breaker = self._get_breaker(provider)

            if not breaker.can_execute():
                logger.warning("circuit_breaker_skip", model=model, provider=provider)
                continue

            try:
                METRICS.llm_calls.inc(phase=phase)
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
                breaker.record(success=True)

                # Track tokens
                usage = getattr(response, "usage", None)
                self.tracker.record(phase, model, usage)
                if usage and hasattr(usage, "total_tokens"):
                    METRICS.llm_tokens.inc(amount=usage.total_tokens, phase=phase)

                content = response.choices[0].message.content
                if not content:
                    raise LLMProviderError(f"Empty response from {model}")
                return content

            except Exception as e:
                breaker.record(success=False)
                METRICS.llm_errors.inc(phase=phase)
                last_error = e
                logger.warning("llm_call_failed", model=model, error=str(e))

        raise LLMProviderError(
            f"All models failed. Tried: {models_to_try}. Last error: {last_error}"
        )

    def get_tracker(self) -> TokenTracker:
        return self.tracker
