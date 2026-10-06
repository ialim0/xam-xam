"""Interface des traducteurs. Aucun modèle n'est choisi pour l'instant (voir docs/modeles.md :
éviter les licences non commerciales, comme NLLB ou SeamlessM4T en CC BY-NC 4.0)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from xamxam.errors import XamXamError


class TranslationError(XamXamError):
    """Traduction impossible ou incorrecte (marqueurs de termes perdus ou dupliqués)."""


class Translator(ABC):
    name: str

    @abstractmethod
    def translate(self, text: str, *, source: str = "fr", target: str = "wo") -> str:
        """Traduit `text` ; les marqueurs ⟦T1⟧, ⟦T2⟧… doivent être recopiés tels quels."""
