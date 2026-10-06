"""Lexique Xam-Xam : chargement, validation et recherche des termes scientifiques."""

from xamxam.lexicon.index import LexiconIndex, TermMatch
from xamxam.lexicon.loader import LexiconError, load_lexicon
from xamxam.lexicon.schema import Lexicon, Term, normalize_form

__all__ = [
    "Lexicon",
    "LexiconError",
    "LexiconIndex",
    "Term",
    "TermMatch",
    "load_lexicon",
    "normalize_form",
]
