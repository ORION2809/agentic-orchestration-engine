"""Phase 1: Clarifier Agent — asks targeted questions to build game requirements."""

from __future__ import annotations

from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.models.schemas import (
    Assumption,
    ClarificationResult,
    GameRequirements,
)
from app.models.state import RunContext

logger = structlog.get_logger()

# Requirement dimensions the clarifier works to fill.
DIMENSIONS = [
    {"key": "genre", "required": True, "label": "Genre / game type"},
    {"key": "core_objective", "required": True, "label": "Core objective"},
    {"key": "controls", "required": True, "label": "Controls"},
    {"key": "win_condition", "required": True, "label": "Win condition"},
    {"key": "lose_condition", "required": True, "label": "Lose condition"},
    {"key": "difficulty", "required": False, "label": "Difficulty"},
    {"key": "visual_style", "required": False, "label": "Visual style"},
    {"key": "framework_preference", "required": False, "label": "Framework"},
    {"key": "sound", "required": False, "label": "Sound"},
    {"key": "num_players", "required": False, "label": "Number of players"},
]


def compute_confidence(resolved: dict[str, Any]) -> float:
    """Compute confidence score based on filled dimensions."""
    required = [d for d in DIMENSIONS if d["required"]]
    optional = [d for d in DIMENSIONS if not d["required"]]

    filled_required = sum(
        1 for d in required if resolved.get(d["key"]) and str(resolved[d["key"]]).strip()
    )
    filled_optional = sum(
        1 for d in optional if resolved.get(d["key"]) and str(resolved[d["key"]]).strip()
    )

    required_score = filled_required / max(len(required), 1)
    optional_score = filled_optional / max(len(optional), 1)

    return round(0.8 * required_score + 0.2 * optional_score, 2)


class ClarifierAgent(BaseAgent):
    """Asks clarifying questions to extract game requirements from an ambiguous idea."""

    PHASE_NAME = "clarifier"

    def run(self, context: RunContext) -> ClarificationResult:
        idea = context.original_idea
        logger.info("clarifier_start", idea=idea)

        # Step 1: Extract what's already clear from the prompt
        resolved = self._extract_initial(idea)
        all_questions: list[str] = []
        all_answers: dict[str, str] = {}
        round_num = 0

        # Step 2: Clarification loop
        for round_num in range(1, self.config.max_clarification_rounds + 1):
            confidence = compute_confidence(resolved)
            logger.info(
                "clarification_round",
                round=round_num,
                confidence=confidence,
            )

            if confidence >= self.config.confidence_threshold:
                break

            # Generate questions for missing required dimensions
            missing = self._get_missing_dimensions(resolved)
            if not missing:
                break

            questions = self._generate_questions(idea, resolved, missing, round_num)
            if not questions:
                break

            all_questions.extend(questions)

            # Get answers
            answers = self._get_answers(questions)
            all_answers.update(answers)

            # Merge answers into resolved requirements
            resolved = self._merge_answers(resolved, answers)

        # Step 3: Fill remaining gaps with explicit assumptions
        assumptions = self._fill_defaults(resolved)

        final_confidence = compute_confidence(resolved)
        logger.info(
            "clarifier_done",
            confidence=final_confidence,
            assumptions=len(assumptions),
        )

        return ClarificationResult(
            questions_asked=all_questions,
            user_answers=all_answers,
            resolved_requirements=GameRequirements(**resolved),
            assumptions=assumptions,
            confidence_score=final_confidence,
            rounds_used=min(round_num, self.config.max_clarification_rounds),
        )

    def _extract_initial(self, idea: str) -> dict[str, Any]:
        """Use LLM to extract what requirements are already clear from the idea."""
        system_prompt = self.load_prompt("clarifier_system.md")
        user_prompt = f"""Analyze this game idea and extract as many requirements as you can.
Return a JSON object with these keys (leave empty string "" for anything unclear):
- genre: the game genre/type
- core_objective: what the player does
- controls: how the player interacts (keyboard/mouse/etc)
- win_condition: how to win
- lose_condition: how to lose
- difficulty: difficulty level or progression
- visual_style: visual art style
- framework_preference: vanilla or phaser
- sound: sound design
- num_players: single or multi player

Game idea: "{idea}"

Return ONLY the JSON object, no other text."""

        try:
            result = self.call_structured(
                messages=[
                    {"role": "system", "content": system_prompt or "You are a game design analyst."},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=GameRequirements,
            )
            return result.model_dump()
        except Exception as e:
            logger.warning("initial_extraction_failed", error=str(e))
            return {}

    def _get_missing_dimensions(self, resolved: dict[str, Any]) -> list[dict]:
        """Identify which required dimensions are still missing."""
        missing = []
        for dim in DIMENSIONS:
            if dim["required"]:
                val = resolved.get(dim["key"], "")
                if not val or not str(val).strip():
                    missing.append(dim)
        return missing

    def _generate_questions(
        self,
        idea: str,
        resolved: dict[str, Any],
        missing: list[dict],
        round_num: int,
    ) -> list[str]:
        """Use LLM to generate targeted questions for missing dimensions."""
        missing_labels = ", ".join(d["label"] for d in missing[:4])

        prompt = f"""You are clarifying requirements for a browser game.

Original idea: "{idea}"
Already known: {resolved}
Missing information: {missing_labels}
Round: {round_num}

Generate 2-4 concise, specific questions to fill the missing information.
Return ONLY the questions, one per line. No numbering, no extra text."""

        try:
            response = self.call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a game design expert. Ask concise, targeted questions.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            questions = [q.strip() for q in response.strip().split("\n") if q.strip()]
            return questions[:4]  # max 4 questions per round
        except Exception as e:
            logger.warning("question_generation_failed", error=str(e))
            return []

    def _get_answers(self, questions: list[str]) -> dict[str, str]:
        """Get answers — interactive stdin or auto-fill in batch mode."""
        answers = {}
        if self.config.batch_mode:
            # In batch mode: LLM answers its own questions with reasonable defaults
            for q in questions:
                answers[q] = self._auto_answer(q)
        else:
            # Interactive mode: ask user
            for q in questions:
                try:
                    print(f"\n  ? {q}")
                    answer = input("  > ").strip()
                    answers[q] = answer if answer else "no preference"
                except (EOFError, KeyboardInterrupt):
                    answers[q] = "no preference"
        return answers

    def _auto_answer(self, question: str) -> str:
        """Generate a reasonable default answer in batch mode."""
        try:
            response = self.call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are helping design a simple browser game. "
                            "Give a brief, reasonable default answer. "
                            "Keep it simple and achievable with vanilla JS."
                        ),
                    },
                    {"role": "user", "content": question},
                ]
            )
            return response.strip()[:200]
        except Exception:
            return "no preference"

    def _merge_answers(
        self, resolved: dict[str, Any], answers: dict[str, str]
    ) -> dict[str, Any]:
        """Merge user answers back into resolved requirements via LLM."""
        answers_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in answers.items())
        prompt = f"""Given these Q&A and existing requirements, update the requirements JSON.

Existing: {resolved}

New Q&A:
{answers_text}

Return a JSON with the same keys as before, updated with the new information.
Keep existing values that aren't contradicted."""

        try:
            result = self.call_structured(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a game requirements analyst. Merge new answers into existing requirements.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_model=GameRequirements,
            )
            return result.model_dump()
        except Exception as e:
            logger.warning("merge_answers_failed", error=str(e))
            return resolved

    def _fill_defaults(self, resolved: dict[str, Any]) -> list[Assumption]:
        """Fill any remaining gaps with explicit default assumptions."""
        defaults = {
            "genre": ("action", "No genre specified; defaulting to action"),
            "core_objective": (
                "survive as long as possible",
                "No objective specified; defaulting to survival",
            ),
            "controls": (
                "keyboard arrows + space",
                "No controls specified; defaulting to keyboard",
            ),
            "win_condition": (
                "reach target score",
                "No win condition; defaulting to score-based",
            ),
            "lose_condition": (
                "lose all lives or hit obstacle",
                "No lose condition; defaulting to lives-based",
            ),
            "difficulty": ("medium, progressive", "Default difficulty"),
            "visual_style": ("minimalist CSS shapes", "Default visual style"),
            "framework_preference": ("vanilla", "Vanilla JS for simplicity"),
            "sound": ("none", "No sound for simplicity"),
            "num_players": ("single player", "Default single player"),
        }

        assumptions = []
        for key, (default_val, reason) in defaults.items():
            current = resolved.get(key, "")
            if not current or not str(current).strip():
                resolved[key] = default_val
                assumptions.append(
                    Assumption(dimension=key, assumed_value=default_val, reason=reason)
                )

        return assumptions
