"""Sortie structurée : extraction du JSON d'une réponse texte, validation, réparation."""

from __future__ import annotations

import re

from pydantic import ValidationError

from xamxam.llm.base import LLMError
from xamxam.llm.schema import MathSolution

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

REPAIR_INSTRUCTION = (
    "Ta réponse précédente n'est pas un objet JSON valide conforme au schéma "
    "({errors}). Renvoie uniquement l'objet JSON corrigé, sans texte autour."
)


class InvalidStructuredOutputError(LLMError):
    """La réponse ne contient pas un JSON conforme : décrit les erreurs sans le contenu."""


def extract_json_text(text: str) -> str:
    """Isole l'objet JSON d'une réponse : bloc ```json```, ou de la 1re accolade à la dernière."""
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise InvalidStructuredOutputError("aucun objet JSON trouvé")
    return text[start : end + 1]


def parse_solution_text(text: str) -> MathSolution:
    try:
        return MathSolution.model_validate_json(extract_json_text(text))
    except ValidationError as exc:
        raise InvalidStructuredOutputError(_describe(exc)) from exc


def _describe(exc: ValidationError) -> str:
    # Emplacements et types d'erreur seulement : jamais les valeurs (contenu de l'élève).
    locations = sorted({".".join(str(p) for p in e["loc"]) or "racine" for e in exc.errors()})
    return f"{exc.error_count()} erreur(s) : {', '.join(locations[:8])}"
