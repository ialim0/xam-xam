"""Lexique Xam-Xam : chargement, validation et recherche des termes scientifiques."""

from xamxam.lexicon.index import LexiconIndex, TermMatch
from xamxam.lexicon.loader import LexiconError, load_lexicon
from xamxam.lexicon.schema import (
    VALIDATED_AND_DRAFT,
    VALIDATED_ONLY,
    Lexicon,
    Term,
    TermStatus,
    normalize_form,
)

__all__ = [
    "VALIDATED_AND_DRAFT",
    "VALIDATED_ONLY",
    "Lexicon",
    "LexiconError",
    "LexiconIndex",
    "Term",
    "TermMatch",
    "TermStatus",
    "load_lexicon",
    "normalize_form",
]
