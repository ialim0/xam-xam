"""Interface commune aux modèles de langage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from xamxam.errors import XamXamError
from xamxam.llm.schema import MathSolution


class LLMError(XamXamError):
    """Appel au modèle impossible, ou réponse non conforme au schéma."""


class LLMConfigurationError(LLMError):
    """Configuration du modèle invalide (provider inconnu, modèle non autorisé…)."""


@dataclass(frozen=True)
class ProblemInput:
    """Ce que l'élève a envoyé, plus une éventuelle consigne de correction."""

    image: bytes | None = None
    image_mime_type: str | None = None
    transcript: str | None = None  # transcription de la note vocale
    text: str | None = None  # message texte éventuel
    # Second essai après un désaccord avec la vérification sympy.
    previous: MathSolution | None = None
    correction: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.image or self.transcript or self.text)


@dataclass(frozen=True)
class CallStats:
    """Mesures d'un appel, pour l'évaluation des modèles (aucun contenu)."""

    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1  # 2 si une réparation du JSON a été nécessaire
    used_tool: bool = False  # JSON forcé par l'appel d'outils

    @property
    def json_valid_first_try(self) -> bool:
        return self.attempts == 1


@dataclass(frozen=True)
class LLMResult:
    solution: MathSolution
    stats: CallStats


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, problem: ProblemInput) -> LLMResult:
        """Analyse l'exercice et retourne une solution validée, avec ses mesures."""

    def solve(self, problem: ProblemInput) -> MathSolution:
        return self.generate(problem).solution
