"""Tables de lecture : comment chaque langue lit les symboles, nombres et unités.

Seule la table française existe pour l'instant. Une table wolof devra être construite
avec des locuteurs natifs : on n'invente aucune lecture.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from xamxam.errors import XamXamError
from xamxam.normalize.numbers import spell_french_number


class UnknownLanguageError(XamXamError, ValueError):
    """Aucune table de lecture pour la langue demandée."""


@dataclass(frozen=True)
class ReadingTable:
    """Vocabulaire utilisé par le normaliseur pour une langue de lecture."""

    language: str
    spell_number: Callable[[int], str]
    decimal_word: str
    fraction_word: str
    sqrt_words: str
    power_word: str
    minus_word: str
    # Exposants ayant une lecture dédiée (2 → « au carré »).
    exponent_words: Mapping[int, str]
    # Symboles remplacés par un mot, essayés dans l'ordre (les plus longs d'abord).
    symbol_words: Mapping[str, str]
    # Unité → (singulier, pluriel).
    units: Mapping[str, tuple[str, str]]
    unicode_fractions: Mapping[str, str]

    def exponent(self, n: int) -> str:
        return self.exponent_words.get(n) or f"{self.power_word} {n}"


FRENCH = ReadingTable(
    language="fr",
    spell_number=spell_french_number,
    decimal_word="virgule",
    fraction_word="sur",
    sqrt_words="racine carrée de",
    power_word="puissance",
    minus_word="moins",
    exponent_words=MappingProxyType({2: "au carré", 3: "au cube"}),
    symbol_words=MappingProxyType(
        {
            "//": "parallèle à",
            "∥": "parallèle à",
            "⊥": "perpendiculaire à",
            "≤": "inférieur ou égal à",
            "≥": "supérieur ou égal à",
            "≠": "différent de",
            "≈": "environ égal à",
            "=": "égale",
            "<": "inférieur à",
            ">": "supérieur à",
            "×": "fois",
            "÷": "divisé par",
            "+": "plus",
            "−": "moins",
            "%": "pour cent",
            "π": "pi",
        }
    ),
    units=MappingProxyType(
        {
            "km/h": ("kilomètre par heure", "kilomètres par heure"),
            "mm²": ("millimètre carré", "millimètres carrés"),
            "cm²": ("centimètre carré", "centimètres carrés"),
            "m²": ("mètre carré", "mètres carrés"),
            "km²": ("kilomètre carré", "kilomètres carrés"),
            "cm³": ("centimètre cube", "centimètres cubes"),
            "m³": ("mètre cube", "mètres cubes"),
            "mm": ("millimètre", "millimètres"),
            "cm": ("centimètre", "centimètres"),
            "dm": ("décimètre", "décimètres"),
            "km": ("kilomètre", "kilomètres"),
            "m": ("mètre", "mètres"),
            "kg": ("kilogramme", "kilogrammes"),
            "g": ("gramme", "grammes"),
            "mL": ("millilitre", "millilitres"),
            "cL": ("centilitre", "centilitres"),
            "L": ("litre", "litres"),
            "min": ("minute", "minutes"),
            "h": ("heure", "heures"),
            "s": ("seconde", "secondes"),
            "°C": ("degré Celsius", "degrés Celsius"),
            "°": ("degré", "degrés"),
        }
    ),
    unicode_fractions=MappingProxyType({"½": "un demi", "¼": "un quart", "¾": "trois quarts"}),
)

_TABLES: dict[str, ReadingTable] = {FRENCH.language: FRENCH}


def get_table(language: str) -> ReadingTable:
    """Retourne la table de lecture d'une langue (UnknownLanguageError si elle n'existe pas)."""
    try:
        return _TABLES[language]
    except KeyError:
        available = ", ".join(sorted(_TABLES))
        raise UnknownLanguageError(
            f"Aucune table de lecture pour « {language} » (disponibles : {available}). "
            "Les tables pour le wolof, le pulaar et le sérère restent à construire "
            "avec des locuteurs natifs."
        ) from None
