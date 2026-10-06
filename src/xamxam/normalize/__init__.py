"""Conversion des expressions mathématiques en texte lisible par un TTS."""

from xamxam.normalize.normalizer import MathNormalizer, NormalizationMode
from xamxam.normalize.numbers import spell_french_number, spell_wolof_number
from xamxam.normalize.tables import (
    FRENCH,
    NumberLanguage,
    ReadingTable,
    UnknownLanguageError,
    get_table,
)

__all__ = [
    "FRENCH",
    "MathNormalizer",
    "NormalizationMode",
    "NumberLanguage",
    "ReadingTable",
    "UnknownLanguageError",
    "get_table",
    "spell_french_number",
    "spell_wolof_number",
]
