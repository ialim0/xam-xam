"""Conversion des expressions mathématiques en texte lisible par un TTS."""

from xamxam.normalize.normalizer import MathNormalizer, NormalizationMode
from xamxam.normalize.numbers import spell_french_number
from xamxam.normalize.tables import FRENCH, ReadingTable, UnknownLanguageError, get_table

__all__ = [
    "FRENCH",
    "MathNormalizer",
    "NormalizationMode",
    "ReadingTable",
    "UnknownLanguageError",
    "get_table",
    "spell_french_number",
]
