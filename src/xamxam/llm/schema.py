"""Contrat JSON de la réponse du modèle (champs en français, attributs Python en anglais)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SolutionStatus(StrEnum):
    OK = "ok"
    UNREADABLE = "image_illisible"
    OFF_TOPIC = "hors_sujet"


class Notion(StrEnum):
    PYTHAGORE = "pythagore"
    THALES = "thales"
    OTHER = "autre"


class CalculationKind(StrEnum):
    """Calculs vérifiables. Les noms des données attendues sont rappelés dans le prompt."""

    PYTHAGORE_HYPOTENUSE = "pythagore_hypotenuse"  # cote1, cote2 → hypoténuse
    PYTHAGORE_SIDE = "pythagore_cote"  # hypotenuse, cote → autre côté
    PYTHAGORE_CONVERSE = "pythagore_reciproque"  # a, b, c → « oui » si rectangle
    THALES_LENGTH = "thales_longueur"  # a, b, c avec a/b = c/x → x
    THALES_CONVERSE = "thales_reciproque"  # a, b, c, d → « oui » si a/b = c/d
    NONE = "aucun"


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class KnownValue(_Model):
    name: str = Field(alias="nom")
    value: float = Field(alias="valeur")


class Calculation(_Model):
    kind: CalculationKind = Field(alias="type")
    values: list[KnownValue] = Field(alias="donnees", description="Longueurs lues dans l'énoncé.")
    result: str = Field(alias="resultat", description="Valeur trouvée seule, ex. « √52 ≈ 7,21 ».")

    def value(self, name: str) -> float | None:
        return next((v.value for v in self.values if v.name == name), None)


class MathSolution(_Model):
    status: SolutionStatus = Field(alias="statut")
    statement: str = Field(alias="enonce")
    notion: Notion
    steps: list[str] = Field(alias="etapes")
    final_answer: str = Field(alias="reponse_finale")
    key_terms: list[str] = Field(alias="termes_cles")
    explanation_wo: str = Field(alias="explication_wo")
    calculation: Calculation = Field(alias="calcul")
    # Rempli seulement en mode traduction (TRANSLATE_FROM_FRENCH) : explication en français simple.
    explanation_fr: str = Field(default="", alias="explication_fr")


def _inline_refs(node: Any, definitions: dict[str, Any]) -> Any:
    """Remplace les $ref par leur définition : schéma autonome, plus sûr pour les LLM."""
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(definitions[node["$ref"].rsplit("/", 1)[-1]], definitions)
        return {k: _inline_refs(v, definitions) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(item, definitions) for item in node]
    return node


def solution_json_schema() -> dict[str, Any]:
    """Schéma JSON de MathSolution avec les noms de champs français, sans références."""
    schema = MathSolution.model_json_schema(by_alias=True)
    return _inline_refs(schema, schema.get("$defs", {}))
