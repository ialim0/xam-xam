"""Chaîne Xam-Xam complète : normalisation mathématique puis réécriture par le lexique."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from xamxam.lexicon import Lexicon, LexiconIndex, load_lexicon
from xamxam.normalize import MathNormalizer, NumberLanguage, get_table
from xamxam.pronounce import PronunciationRewriter, Replacement


@dataclass(frozen=True)
class PreparedText:
    """Résultat de chaque étape, pour pouvoir comparer et déboguer."""

    source: str
    normalized: str
    text: str
    replacements: tuple[Replacement, ...]


class XamXamPipeline:
    """Prépare un texte pour le TTS.

    La normalisation passe en premier : un terme produit par elle (ex. « racine carrée »)
    peut ainsi être corrigé ensuite par le lexique.
    """

    def __init__(
        self,
        lexicon: Lexicon,
        *,
        reading_language: str = "fr",
        number_language: NumberLanguage = NumberLanguage.FRENCH,
    ) -> None:
        self._index = LexiconIndex(lexicon)
        self._normalizer = MathNormalizer(
            get_table(reading_language), number_language=number_language
        )
        self._rewriter = PronunciationRewriter(self._index)

    @classmethod
    def from_lexicon_file(
        cls,
        path: str | Path,
        *,
        reading_language: str = "fr",
        number_language: NumberLanguage = NumberLanguage.FRENCH,
    ) -> XamXamPipeline:
        return cls(
            load_lexicon(path), reading_language=reading_language, number_language=number_language
        )

    @property
    def index(self) -> LexiconIndex:
        return self._index

    def prepare(self, text: str) -> PreparedText:
        source = unicodedata.normalize("NFC", text)
        normalized = self._normalizer.normalize(source)
        rewritten = self._rewriter.rewrite(normalized)
        return PreparedText(
            source=source,
            normalized=normalized,
            text=rewritten.text,
            replacements=rewritten.replacements,
        )
