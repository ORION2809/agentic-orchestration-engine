"""Abstract base agent with LLM call integration and token tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

from app.config import Config
from app.llm.provider import LLMProvider
from app.llm.structured import StructuredLLM
from app.models.state import RunContext

logger = structlog.get_logger()


class BaseAgent(ABC):
    """Base class for all agents.

    Provides:
        - Access to LLM provider (raw completion + structured output)
        - Prompt loading from markdown files
        - Phase-specific temperature settings
    """

    PHASE_NAME: str = "base"

    def __init__(
        self,
        config: Config,
        llm: LLMProvider,
        structured_llm: StructuredLLM,
    ):
        self.config = config
        self.llm = llm
        self.structured_llm = structured_llm

    @abstractmethod
    def run(self, context: RunContext) -> Any:
        """Execute this agent's logic. Must be implemented by subclasses."""
        ...

    def load_prompt(self, filename: str) -> str:
        """Load a prompt template from the prompts directory."""
        path = self.config.prompt_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("prompt_not_found", filename=filename)
        return ""

    def get_temperature(self) -> float:
        """Get the configured temperature for this agent's phase."""
        return self.config.phase_temperatures.get(self.PHASE_NAME, 0.3)

    def call_llm(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Make a raw LLM call with phase tracking."""
        return self.llm.complete(
            messages=messages,
            phase=self.PHASE_NAME,
            temperature=self.get_temperature(),
            **kwargs,
        )

    def call_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        """Make a structured LLM call returning a validated Pydantic model."""
        return self.structured_llm.create(
            messages=messages,
            response_model=response_model,
            phase=self.PHASE_NAME,
            temperature=self.get_temperature(),
            **kwargs,
        )
