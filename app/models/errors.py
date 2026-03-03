"""Custom exception hierarchy and error categories."""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Categorized error types for recovery matrix."""

    LLM_TIMEOUT = "llm_timeout"
    LLM_PARSE_FAILURE = "llm_parse_failure"
    LLM_REFUSAL = "llm_refusal"
    LLM_TRUNCATION = "llm_truncation"
    VALIDATION_SYNTAX = "validation_syntax"
    VALIDATION_STRUCT = "validation_struct"
    VALIDATION_RUNTIME = "validation_runtime"
    VALIDATION_LINKAGE = "validation_linkage"
    STATE_VIOLATION = "state_violation"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"


class GameBuilderError(Exception):
    """Base exception for the game builder system."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory | None = None,
        **context: object,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.context = context


class LLMProviderError(GameBuilderError):
    """Raised when all LLM providers fail."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.LLM_TIMEOUT, **context)


class LLMParseError(GameBuilderError):
    """Raised when LLM output cannot be parsed into the expected schema."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.LLM_PARSE_FAILURE, **context)


class LLMRefusalError(GameBuilderError):
    """Raised when LLM refuses a request due to content policy."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.LLM_REFUSAL, **context)


class LLMTruncationError(GameBuilderError):
    """Raised when LLM output is truncated (hit max tokens)."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.LLM_TRUNCATION, **context)


class StateViolationError(GameBuilderError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.STATE_VIOLATION, **context)


class BudgetExhaustedError(GameBuilderError):
    """Raised when the token/cost budget is depleted."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.BUDGET_EXHAUSTED, **context)


class CircuitBreakerOpenError(GameBuilderError):
    """Raised when a circuit breaker is open and no fallback is available."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.CIRCUIT_BREAKER_OPEN, **context)


class ValidationError(GameBuilderError):
    """Raised for validation failures."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.VALIDATION_STRUCT,
        **context: object,
    ):
        super().__init__(message, category, **context)


class CheckpointCorruptError(GameBuilderError):
    """Raised when a checkpoint file is unreadable or corrupted."""

    def __init__(self, message: str, **context: object):
        super().__init__(message, ErrorCategory.CHECKPOINT_CORRUPT, **context)
