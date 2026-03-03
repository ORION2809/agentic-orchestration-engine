"""Observability metrics — Prometheus-compatible counters, histograms, and gauges."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Counter:
    """Monotonically increasing counter."""
    name: str
    help_text: str
    _values: dict[tuple[str, ...], float] = field(default_factory=lambda: defaultdict(float))

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] += amount

    def get(self, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0.0)

    def total(self) -> float:
        return sum(self._values.values())


@dataclass
class Histogram:
    """Tracks distribution of observed values in predefined buckets."""
    name: str
    help_text: str
    buckets: list[float] = field(default_factory=lambda: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0])
    _observations: list[tuple[float, dict[str, str]]] = field(default_factory=list)

    def observe(self, value: float, **labels: str) -> None:
        self._observations.append((value, labels))

    def get_stats(self, **labels: str) -> dict[str, float]:
        values = [v for v, l in self._observations if all(l.get(k) == v2 for k, v2 in labels.items())]
        if not values:
            return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }


@dataclass
class Gauge:
    """A value that can go up and down."""
    name: str
    help_text: str
    _values: dict[tuple[str, ...], float] = field(default_factory=lambda: defaultdict(float))

    def set(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] = value

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] += amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] -= amount

    def get(self, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        return self._values.get(key, 0.0)


class MetricsRegistry:
    """Central registry for all application metrics."""

    def __init__(self) -> None:
        # Run-level counters
        self.runs_started = Counter("runs_started_total", "Total runs started")
        self.runs_completed = Counter("runs_completed_total", "Total runs completed")
        self.runs_failed = Counter("runs_failed_total", "Total runs failed")
        self.runs_fallback = Counter("runs_fallback_total", "Runs that used deterministic fallback")

        # LLM counters
        self.llm_calls = Counter("llm_calls_total", "Total LLM API calls")
        self.llm_errors = Counter("llm_errors_total", "Total LLM API errors")
        self.llm_tokens = Counter("llm_tokens_total", "Total tokens consumed")

        # Phase-level histograms
        self.phase_duration = Histogram(
            "phase_duration_seconds",
            "Duration of each pipeline phase",
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
        )
        self.llm_latency = Histogram(
            "llm_latency_seconds",
            "LLM API call latency",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )

        # Gauges
        self.active_runs = Gauge("active_runs", "Currently active runs")
        self.circuit_breaker_state = Gauge("circuit_breaker_state", "Circuit breaker states (0=closed, 1=open, 0.5=half-open)")

        # Build attempt tracking
        self.build_attempts = Counter("build_attempts_total", "Total build attempts")
        self.repair_cycles = Counter("repair_cycles_total", "Total repair cycles executed")
        self.escalations = Counter("model_escalations_total", "Model escalation events")
        self.simplifications = Counter("simplifications_total", "Plan simplification events")

        # Validation
        self.validation_checks = Counter("validation_checks_total", "Total validation checks run")
        self.validation_blockers = Counter("validation_blockers_total", "Blocker-level validation failures")

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of all metrics for logging/display."""
        return {
            "runs": {
                "started": self.runs_started.total(),
                "completed": self.runs_completed.total(),
                "failed": self.runs_failed.total(),
                "fallback": self.runs_fallback.total(),
                "active": self.active_runs.get(),
            },
            "llm": {
                "calls": self.llm_calls.total(),
                "errors": self.llm_errors.total(),
                "tokens": self.llm_tokens.total(),
                "latency": self.llm_latency.get_stats(),
            },
            "builds": {
                "attempts": self.build_attempts.total(),
                "repairs": self.repair_cycles.total(),
                "escalations": self.escalations.total(),
                "simplifications": self.simplifications.total(),
            },
            "validation": {
                "checks": self.validation_checks.total(),
                "blockers": self.validation_blockers.total(),
            },
        }


# Singleton instance
METRICS = MetricsRegistry()
