"""Schéma du lexique (validation pydantic)."""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Chaîne nettoyée de ses espaces de bord et non vide.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def normalize_form(text: str) -> str:
    """Forme canonique d'un terme pour les comparaisons : NFC, minuscules, espaces simplifiés."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


class TermStatus(StrEnum):
    """Statut de la prononciation d'un terme."""

    DRAFT = "brouillon"  # proposition non validée
    VALIDATED = "valide"  # validée par un locuteur natif


class Term(BaseModel):
    """Un terme scientifique et sa prononciation (validée ou brouillon)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    term: NonEmptyStr = Field(description="Forme écrite du terme, ex. « triangle rectangle ».")
    pronunciation: NonEmptyStr | None = Field(
        default=None,
        description="Réécriture à envoyer au TTS. Absente : le terme n'est jamais réécrit.",
    )
    status: TermStatus = Field(default=TermStatus.DRAFT, alias="statut")
    notion: str | None = Field(default=None, description="Notion associée, ex. « pythagore ».")
    aliases: tuple[NonEmptyStr, ...] = Field(
        default=(), description="Autres graphies reconnues (pluriel, variantes)."
    )
    validated_by: str = Field(
        default="", description="Locuteur natif ayant validé la prononciation (vide = à valider)."
    )
    notes: str = ""
    # Champs repris du lexique source (schéma id / terme_fr / domaine…), conservés tels quels.
    source_id: str | None = Field(default=None, alias="id")
    domain: str | None = Field(default=None, alias="domaine")
    subdomain: str | None = Field(default=None, alias="sous_domaine")
    level: str | None = Field(default=None, alias="niveau_indicatif")
    english_reading_risk: str | int | bool | None = Field(
        default=None, alias="risque_lecture_anglaise"
    )
    wolof_equivalent: str | None = Field(default=None, alias="equivalent_wo")
    test_sentences: tuple[str, ...] = Field(default=(), alias="phrases_test")
    # Tout autre champ du lexique source, pour ne rien perdre à la conversion.
    extra: dict[str, Any] = Field(default_factory=dict, alias="autres")

    @model_validator(mode="after")
    def _validated_terms_are_complete(self) -> Term:
        if self.status is TermStatus.VALIDATED and not (
            self.pronunciation and self.validated_by.strip()
        ):
            raise ValueError(
                f"« {self.term} » est marqué valide sans prononciation ou sans validateur"
            )
        return self

    @property
    def forms(self) -> tuple[str, ...]:
        """Toutes les graphies reconnues : le terme puis ses alias."""
        return (self.term, *self.aliases)

    @property
    def is_validated(self) -> bool:
        return self.status is TermStatus.VALIDATED

    def is_applicable(self, statuses: frozenset[TermStatus]) -> bool:
        """Le terme est réécrit s'il a une prononciation et un statut accepté."""
        return self.pronunciation is not None and self.status in statuses


class Lexicon(BaseModel):
    """Lexique complet pour une langue cible."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

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


# Statuts appliqués par défaut : uniquement les prononciations validées.
VALIDATED_ONLY = frozenset({TermStatus.VALIDATED})
VALIDATED_AND_DRAFT = frozenset({TermStatus.VALIDATED, TermStatus.DRAFT})
