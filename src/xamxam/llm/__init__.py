"""Résolution d'exercices par un modèle de langage open source, avec sortie JSON validée."""

from xamxam.llm.base import (
    CallStats,
    LLMConfigurationError,
    LLMError,
    LLMProvider,
    LLMResult,
    ProblemInput,
)
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
    "CallStats",
    "KnownValue",
    "LLMConfigurationError",
    "LLMError",
    "LLMProvider",
    "LLMResult",
    "MathSolution",
    "Notion",
    "ProblemInput",
    "SolutionStatus",
]
