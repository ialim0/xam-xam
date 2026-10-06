"""Substitution des termes du lexique par leur prononciation validée."""

from __future__ import annotations

from dataclasses import dataclass

from xamxam.lexicon import LexiconIndex


@dataclass(frozen=True)
class Replacement:
    """Trace d'une substitution, utile pour le débogage et l'évaluation."""

    original: str
    pronunciation: str
    term: str


@dataclass(frozen=True)
class RewriteResult:
    text: str
    replacements: tuple[Replacement, ...]


class PronunciationRewriter:
    """Remplace chaque terme reconnu par sa prononciation ; le reste du texte est conservé."""

    def __init__(self, index: LexiconIndex) -> None:
        self._index = index

    def rewrite(self, text: str) -> RewriteResult:
        parts: list[str] = []
        replacements: list[Replacement] = []
        cursor = 0
        for match in self._index.find_all(text):
            parts.append(text[cursor : match.start])
            parts.append(match.term.pronunciation)
            replacements.append(
                Replacement(
                    original=match.surface,
                    pronunciation=match.term.pronunciation,
                    term=match.term.term,
                )
            )
            cursor = match.end
        parts.append(text[cursor:])
        return RewriteResult(text="".join(parts), replacements=tuple(replacements))
