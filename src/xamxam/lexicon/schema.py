"""Schéma du lexique (validation pydantic)."""

from __future__ import annotations

import unicodedata
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Chaîne nettoyée de ses espaces de bord et non vide.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def normalize_form(text: str) -> str:
    """Forme canonique d'un terme pour les comparaisons : NFC, minuscules, espaces simplifiés."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


class Term(BaseModel):
    """Un terme scientifique et sa prononciation validée."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    term: NonEmptyStr = Field(description="Forme écrite du terme, ex. « triangle rectangle ».")
    pronunciation: NonEmptyStr = Field(
        description="Réécriture à envoyer au TTS pour obtenir la bonne prononciation."
    )
    notion: str | None = Field(default=None, description="Notion associée, ex. « pythagore ».")
    aliases: tuple[NonEmptyStr, ...] = Field(
        default=(), description="Autres graphies reconnues (pluriel, variantes)."
    )
    validated_by: str = Field(
        default="", description="Locuteur natif ayant validé la prononciation (vide = à valider)."
    )
    notes: str = ""

    @property
    def forms(self) -> tuple[str, ...]:
        """Toutes les graphies reconnues : le terme puis ses alias."""
        return (self.term, *self.aliases)

    @property
    def is_validated(self) -> bool:
        return bool(self.validated_by.strip())


class Lexicon(BaseModel):
    """Lexique complet pour une langue cible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: NonEmptyStr
    language: NonEmptyStr = Field(description="Code de la langue cible, ex. « wo ».")
    terms: tuple[Term, ...]

    @model_validator(mode="after")
    def _forms_are_unique(self) -> Lexicon:
        # Une même graphie ne peut pointer que vers un seul terme, sinon la recherche est ambiguë.
        owners: dict[str, str] = {}
        for term in self.terms:
            for form in term.forms:
                key = normalize_form(form)
                if key in owners:
                    raise ValueError(
                        f"la graphie « {form} » est déclarée deux fois "
                        f"(termes « {owners[key]} » et « {term.term} »)"
                    )
                owners[key] = term.term
        return self
