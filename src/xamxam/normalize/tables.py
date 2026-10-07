"""Tables de lecture : comment chaque langue lit les symboles, nombres et unités.

Seule la table française existe pour l'instant. Une table wolof devra être construite
avec des locuteurs natifs : on n'invente aucune lecture.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from xamxam.errors import XamXamError
from xamxam.normalize.numbers import spell_french_number, spell_wolof_number


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
    # Nom des lettres pour les noms de points (A, AB, ABC), écrit pour que la voix wolof
    # le prononce : épelée telle quelle (« A B »), une lettre isolée est avalée par le TTS.
    letter_names: Mapping[str, str]

    def exponent(self, n: int) -> str:
        return self.exponent_words.get(n) or f"{self.power_word} {n}"


# Noms français des lettres en orthographe wolof (B = « bé » → bee), pour les noms de points.
# Mesuré sur le TTS Kiriku le 7 octobre 2026 : « aa bee » est entendu « a b », alors que
# « A B » disparaît. BROUILLON : à confirmer à l'oreille par un locuteur, lettre par lettre.
# fmt: off
_FRENCH_LETTER_NAMES = {
    "A": "aa", "B": "bee", "C": "see", "D": "dee", "E": "ë", "F": "ef",
    "G": "jee", "H": "aas", "I": "ii", "J": "jii", "K": "kaa", "L": "el",
    "M": "em", "N": "en", "O": "oo", "P": "pee", "Q": "ku", "R": "er",
    "S": "es", "T": "tee", "U": "u", "V": "wee", "W": "dubal wee", "X": "iks",
    "Y": "igrek", "Z": "sed",
}
# fmt: on

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
    letter_names=MappingProxyType(_FRENCH_LETTER_NAMES),
)

_TABLES: dict[str, ReadingTable] = {FRENCH.language: FRENCH}


class NumberLanguage(StrEnum):
    """Langue dans laquelle les nombres sont écrits en lettres avant le TTS.

    Le TTS Kiriku ne lit lui-même que 0 à 10 (en français) : tout nombre plus grand
    doit être écrit en lettres, sinon il est perdu. Le mode choisi s'applique à tous
    les nombres pour que la lecture reste homogène dans une phrase.
    """

    FRENCH = "fr"
    WOLOF = "wo"


NUMBER_SPELLERS: Mapping[NumberLanguage, Callable[[int], str]] = MappingProxyType(
    {NumberLanguage.FRENCH: spell_french_number, NumberLanguage.WOLOF: spell_wolof_number}
)


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
