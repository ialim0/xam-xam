"""Substitution des termes du lexique par leur prononciation validée."""

from __future__ import annotations

from dataclasses import dataclass

from xamxam.lexicon import VALIDATED_AND_DRAFT, LexiconIndex, TermStatus


@dataclass(frozen=True)
class Replacement:
    """Trace d'une substitution, utile pour le débogage et l'évaluation."""

    original: str
    pronunciation: str
    term: str
    status: TermStatus


@dataclass(frozen=True)
class RewriteResult:
    text: str
    replacements: tuple[Replacement, ...]


class PronunciationRewriter:
    """Remplace chaque terme reconnu par sa prononciation ; le reste du texte est conservé.

    La recherche porte sur tout le lexique : un terme composé non applicable (brouillon
    exclu, ou sans prononciation) est laissé intact en entier, sans que ses mots soient
    réécrits séparément (« triangle rectangle » brouillon ne devient pas « tiriyaangal
    rectangle » parce que « triangle » seul est validé).
    """

    def __init__(
        self, index: LexiconIndex, applied_statuses: frozenset[TermStatus] = VALIDATED_AND_DRAFT
    ) -> None:
        self._index = index
        self._applied_statuses = applied_statuses

    def rewrite(self, text: str) -> RewriteResult:
        parts: list[str] = []
        replacements: list[Replacement] = []
        cursor = 0
        for match in self._index.find_all(text):
            if not match.term.is_applicable(self._applied_statuses):
                continue
            parts.append(text[cursor : match.start])
            parts.append(match.term.pronunciation)
            replacements.append(
                Replacement(
                    original=match.surface,
                    pronunciation=match.term.pronunciation,
                    term=match.term.term,
                    status=match.term.status,
                )
            )
            cursor = match.end
        parts.append(text[cursor:])
        return RewriteResult(text="".join(parts), replacements=tuple(replacements))
