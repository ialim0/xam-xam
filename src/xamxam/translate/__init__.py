"""Traduction optionnelle français → wolof, avec protection des termes du lexique."""

from xamxam.translate.base import TranslationError, Translator
from xamxam.translate.protect import (
    ProtectedText,
    protect_terms,
    restore_terms,
    translate_protected,
)

__all__ = [
    "ProtectedText",
    "TranslationError",
    "Translator",
    "protect_terms",
    "restore_terms",
    "translate_protected",
]
