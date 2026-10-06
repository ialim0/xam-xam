"""Recherche des termes du lexique dans un texte."""

from __future__ import annotations

import re
from dataclasses import dataclass

from xamxam.lexicon.schema import Lexicon, Term, normalize_form


@dataclass(frozen=True)
class TermMatch:
    """Occurrence d'un terme du lexique dans un texte."""

    start: int
    end: int
    surface: str
    term: Term


def _form_pattern(form: str) -> str:
    # Les espaces internes d'un terme composé tolèrent n'importe quel blanc.
    return r"\s+".join(re.escape(word) for word in form.split())


class LexiconIndex:
    """Index de recherche sur un lexique.

    Les termes composés sont prioritaires : les graphies sont essayées de la plus
    longue à la plus courte, donc « triangle rectangle » l'emporte sur « triangle ».
    La recherche ignore la casse et respecte les frontières de mots
    (« triangles » ne correspond pas à « triangle » sauf s'il est déclaré en alias).
    Le texte doit être en Unicode NFC.
    """

    def __init__(self, lexicon: Lexicon) -> None:
        self._lexicon = lexicon
        self._by_form: dict[str, Term] = {
            normalize_form(form): term for term in lexicon.terms for form in term.forms
        }
        forms = sorted(self._by_form, key=len, reverse=True)
        self._pattern = (
            re.compile(
                r"(?<!\w)(?:" + "|".join(_form_pattern(f) for f in forms) + r")(?!\w)",
                re.IGNORECASE,
            )
            if forms
            else None
        )

    @property
    def lexicon(self) -> Lexicon:
        return self._lexicon

    def lookup(self, text: str) -> Term | None:
        """Retourne le terme correspondant exactement à `text` (terme ou alias), sinon None."""
        return self._by_form.get(normalize_form(text))

    def find_all(self, text: str) -> list[TermMatch]:
        """Retourne les occurrences non chevauchantes des termes, de gauche à droite."""
        if self._pattern is None:
            return []
        return [
            TermMatch(
                start=match.start(),
                end=match.end(),
                surface=match.group(),
                term=self._by_form[normalize_form(match.group())],
            )
            for match in self._pattern.finditer(text)
        ]
