"""Résolution d'exercices par un modèle de langage (Gemini), avec sortie JSON validée."""

from xamxam.llm.base import LLMError, LLMProvider, ProblemInput
from xamxam.llm.schema import (
    Calculation,
    CalculationKind,
    KnownValue,
    MathSolution,
    Notion,
    SolutionStatus,
)

__all__ = [
    "Calculation",
    "CalculationKind",
    "KnownValue",
    "LLMError",
    "LLMProvider",
    "MathSolution",
    "Notion",
    "ProblemInput",
    "SolutionStatus",
]
