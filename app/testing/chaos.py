"""Chaos testing — fault injection for resilience validation."""

from __future__ import annotations

import functools
import random
import time
from enum import Enum
from typing import Any, Callable, TypeVar

import structlog

from app.config import Config
from app.models.errors import LLMProviderError

logger = structlog.get_logger()

F = TypeVar("F", bound=Callable[..., Any])


class FailureType(str, Enum):
    """Types of faults that can be injected."""
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    MALFORMED_JSON = "malformed_json"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"


# Weighted distribution for random fault selection
FAILURE_WEIGHTS: dict[FailureType, float] = {
    FailureType.TIMEOUT: 0.25,
    FailureType.EMPTY_RESPONSE: 0.25,
    FailureType.MALFORMED_JSON: 0.20,
    FailureType.RATE_LIMIT: 0.15,
    FailureType.SERVER_ERROR: 0.15,
}


class ChaosInjector:
    """Injects controlled faults into the LLM pipeline for resilience testing.

    When chaos mode is enabled, each LLM call has a configurable probability
    of experiencing a simulated failure.
    """

    def __init__(self, config: Config) -> None:
        self.enabled = config.chaos_mode
        self.rate = config.chaos_rate
        self._injected_count = 0
        self._skipped_count = 0

    def should_inject(self) -> bool:
        """Decide whether to inject a fault on this call."""
        if not self.enabled:
            return False
        return random.random() < self.rate

    def pick_failure(self) -> FailureType:
        """Select a failure type based on weighted distribution."""
        types = list(FAILURE_WEIGHTS.keys())
        weights = list(FAILURE_WEIGHTS.values())
        return random.choices(types, weights=weights, k=1)[0]

    def inject(self) -> None:
        """Inject a fault — raises or returns corrupted data.

        Always raises an exception to simulate the failure.
        """
        failure = self.pick_failure()
        self._injected_count += 1

        logger.warning(
            "chaos_fault_injected",
            failure_type=failure.value,
            total_injected=self._injected_count,
        )

        if failure == FailureType.TIMEOUT:
            time.sleep(0.5)  # Brief pause to simulate
            raise LLMProviderError("Chaos: simulated timeout", provider="chaos")

        elif failure == FailureType.EMPTY_RESPONSE:
            raise LLMProviderError("Chaos: empty response from provider", provider="chaos")

        elif failure == FailureType.MALFORMED_JSON:
            raise LLMProviderError(
                "Chaos: malformed JSON in response — {invalid json",
                provider="chaos",
            )

        elif failure == FailureType.RATE_LIMIT:
            raise LLMProviderError(
                "Chaos: rate limit exceeded (429)",
                provider="chaos",
            )

        elif failure == FailureType.SERVER_ERROR:
            raise LLMProviderError(
                "Chaos: internal server error (500)",
                provider="chaos",
            )

    def maybe_inject(self) -> None:
        """Conditionally inject a fault based on the configured rate."""
        if self.should_inject():
            self.inject()
        else:
            self._skipped_count += 1

    def get_stats(self) -> dict[str, int]:
        """Return injection statistics."""
        return {
            "injected": self._injected_count,
            "skipped": self._skipped_count,
            "total_checks": self._injected_count + self._skipped_count,
        }


def chaos_wrapper(config: Config) -> Callable[[F], F]:
    """Decorator factory that wraps a function with chaos injection.

    Usage:
        @chaos_wrapper(config)
        def call_llm(...):
            ...

    The decorator will inject faults before the wrapped function executes,
    based on the chaos configuration.
    """
    injector = ChaosInjector(config)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            injector.maybe_inject()
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            injector.maybe_inject()
            return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return wrapper  # type: ignore

    return decorator
