"""Interface commune aux modèles de langage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from xamxam.errors import XamXamError
from xamxam.llm.schema import MathSolution


class LLMError(XamXamError):
    """Appel au modèle impossible, ou réponse non conforme au schéma."""


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


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def solve(self, problem: ProblemInput) -> MathSolution:
        """Analyse l'exercice et retourne une solution validée par le schéma."""
