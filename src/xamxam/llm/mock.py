"""Modèle factice pour les tests : renvoie des solutions préparées, dans l'ordre."""

from __future__ import annotations

from collections.abc import Iterable

from xamxam.llm.base import CallStats, LLMError, LLMProvider, LLMResult, ProblemInput
from xamxam.llm.schema import MathSolution


class ScriptedLLM(LLMProvider):
    name = "mock"
    model = "scripted"

    def __init__(
        self, solutions: Iterable[MathSolution | Exception], stats: CallStats | None = None
    ) -> None:
        self._solutions = list(solutions)
        self._stats = stats or CallStats()
        self.calls: list[ProblemInput] = []

    def generate(self, problem: ProblemInput) -> LLMResult:
        self.calls.append(problem)
        if not self._solutions:
            raise LLMError("ScriptedLLM : plus aucune solution préparée.")
        item = self._solutions.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(item, self._stats)
