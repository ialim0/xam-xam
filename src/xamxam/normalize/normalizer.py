"""Normaliseur d'expressions mathématiques : AB², BC = 5 cm, √25, 3,6, fractions, unités."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum

from xamxam.normalize.tables import FRENCH, ReadingTable

_NUMBER = r"\d+(?:[.,]\d+)?"
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_TO_ASCII_DIGITS = str.maketrans(_SUPERSCRIPT_DIGITS, "0123456789")


class NormalizationMode(StrEnum):
    """Les deux modes comparés lors de l'évaluation."""

    RAW = "raw"  # symboles bruts, texte inchangé
    NORMALIZED = "normalized"  # expressions converties en mots


def _alternation(options: list[str]) -> str:
    # Les options les plus longues d'abord pour que « cm² » passe avant « cm ».
    return "|".join(re.escape(o) for o in sorted(options, key=len, reverse=True))


class MathNormalizer:
    """Réécrit les expressions mathématiques en mots selon une table de lecture.

    Les étapes s'appliquent dans un ordre précis : les unités sont traitées avant
    les exposants (« cm² »), et les nombres sont écrits en lettres en dernier.
    """

    def __init__(self, table: ReadingTable = FRENCH) -> None:
        self._table = table
        self._sqrt = re.compile(r"√\s*(\([^()]*\)|" + _NUMBER + r"|\w+)")
        self._units = re.compile(
            r"(" + _NUMBER + r")\s*(" + _alternation(list(table.units)) + r")(?!\w)"
        )
        self._superscript = re.compile(r"\s*([" + _SUPERSCRIPT_DIGITS + r"]+)")
        self._caret = re.compile(r"\s*\^\s*(\d+)")
        self._unicode_fractions = re.compile(_alternation(list(table.unicode_fractions)))
        self._symbols = re.compile(_alternation(list(table.symbol_words)))
        self._slash = re.compile(r"(?<=[\w)])\s*/\s*(?=[\w(])")
        self._minus_between_numbers = re.compile(r"(?<=\d)\s*-\s*(?=\d)")
        self._standalone_minus = re.compile(r"(?<!\S)-(?=\s|\d)")
        self._decimal = re.compile(r"(\d+)[.,](\d+)")
        self._integer = re.compile(r"\d+")
        self._point_names = re.compile(r"\b[A-Z]{2,3}\b")
        self._steps: tuple[Callable[[str], str], ...] = (
            self._read_square_roots,
            self._read_units,
            self._read_exponents,
            self._read_unicode_fractions,
            self._read_symbols,
            self._read_slashes,
            self._read_minus,
            self._read_decimals,
            self._read_integers,
            self._spell_point_names,
            _tidy_spaces,
        )

    @property
    def table(self) -> ReadingTable:
        return self._table

    def normalize(self, text: str, mode: NormalizationMode = NormalizationMode.NORMALIZED) -> str:
        """Retourne le texte brut (mode RAW) ou converti en mots (mode NORMALIZED)."""
        if mode is NormalizationMode.RAW:
            return text
        for step in self._steps:
            text = step(text)
        return text

    # --- Étapes ---------------------------------------------------------------

    def _read_square_roots(self, text: str) -> str:
        return self._sqrt.sub(lambda m: f" {self._table.sqrt_words} {m.group(1)}", text)

    def _read_units(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            number, unit = match.groups()
            singular, plural = self._table.units[unit]
            # En français, le pluriel commence à 2 (« 1,5 mètre », « 2 mètres »).
            word = plural if float(number.replace(",", ".")) >= 2 else singular
            return f"{number} {word}"

        return self._units.sub(replace, text)

    def _read_exponents(self, text: str) -> str:
        def from_superscript(match: re.Match[str]) -> str:
            return " " + self._table.exponent(int(match.group(1).translate(_TO_ASCII_DIGITS)))

        text = self._superscript.sub(from_superscript, text)
        return self._caret.sub(lambda m: " " + self._table.exponent(int(m.group(1))), text)

    def _read_unicode_fractions(self, text: str) -> str:
        return self._unicode_fractions.sub(
            lambda m: f" {self._table.unicode_fractions[m.group()]} ", text
        )

    def _read_symbols(self, text: str) -> str:
        return self._symbols.sub(lambda m: f" {self._table.symbol_words[m.group()]} ", text)

    def _read_slashes(self, text: str) -> str:
        return self._slash.sub(f" {self._table.fraction_word} ", text)

    def _read_minus(self, text: str) -> str:
        # Un tiret entre deux nombres ou isolé est un « moins » ; dans un mot composé, on le garde.
        text = self._minus_between_numbers.sub(f" {self._table.minus_word} ", text)
        return self._standalone_minus.sub(f"{self._table.minus_word} ", text)

    def _read_decimals(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            integer, decimals = match.groups()
            # Les zéros de tête se lisent un par un : 3,05 → « trois virgule zéro cinq ».
            stripped = decimals.lstrip("0")
            words = [self._table.spell_number(0)] * (len(decimals) - len(stripped))
            if stripped:
                words.append(self._table.spell_number(int(stripped)))
            spelled_integer = self._table.spell_number(int(integer))
            return f"{spelled_integer} {self._table.decimal_word} {' '.join(words)}"

        return self._decimal.sub(replace, text)

    def _read_integers(self, text: str) -> str:
        return self._integer.sub(lambda m: self._table.spell_number(int(m.group())), text)

    def _spell_point_names(self, text: str) -> str:
        # Noms de points et de segments (AB, ABC) : lus lettre par lettre.
        return self._point_names.sub(lambda m: " ".join(m.group()), text)


def _tidy_spaces(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s+([.,;:!?)])", r"\1", text).strip()
