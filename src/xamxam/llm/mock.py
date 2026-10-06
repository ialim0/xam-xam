"""Modèle factice pour les tests : renvoie des solutions préparées, dans l'ordre."""

from __future__ import annotations

from collections.abc import Iterable

from xamxam.llm.base import LLMError, LLMProvider, ProblemInput
from xamxam.llm.schema import MathSolution


class ScriptedLLM(LLMProvider):
    name = "mock"

    def __init__(self, solutions: Iterable[MathSolution]) -> None:
        self._solutions = list(solutions)
        self.calls: list[ProblemInput] = []

    def solve(self, problem: ProblemInput) -> MathSolution:
        self.calls.append(problem)
        if not self._solutions:
            raise LLMError("ScriptedLLM : plus aucune solution préparée.")
        return self._solutions.pop(0)
