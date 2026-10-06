"""Conversion du lexique source (schéma id / terme_fr / domaine / wolof.* / phrases_test)
vers le schéma du dépôt, sans perdre de champ : tout champ non reconnu va dans « autres »."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from xamxam.lexicon.loader import LexiconError
from xamxam.lexicon.schema import Lexicon, TermStatus

# Champs du lexique source et leur équivalent dans le schéma du dépôt (alias JSON).
_TOP_LEVEL = {
    "id": "id",
    "terme_fr": "term",
    "domaine": "domaine",
    "sous_domaine": "sous_domaine",
    "niveau_indicatif": "niveau_indicatif",
    "risque_lecture_anglaise": "risque_lecture_anglaise",
    "phrases_test": "phrases_test",
}
_WOLOF = {
    "equivalent": "equivalent_wo",
    "prononciation": "pronunciation",
    "valide_par": "validated_by",
}
_VALIDATED_WORDS = {"valide", "validé", "validee", "validée", "validated"}
_LIST_KEYS = ("termes", "terms", "entrees", "entries")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entries(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
    raise LexiconError("Lexique source : liste de termes introuvable.")


def convert_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Convertit une entrée source en entrée du dépôt (dictionnaire prêt à valider)."""
    converted: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in entry.items():
        if key in _TOP_LEVEL:
            converted[_TOP_LEVEL[key]] = value
        elif key == "wolof" and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key in _WOLOF:
                    converted[_WOLOF[sub_key]] = sub_value
                elif sub_key != "statut":
                    extra.setdefault("wolof", {})[sub_key] = sub_value
        else:
            extra[key] = value

    converted["term"] = _text(converted.get("term"))
    converted["pronunciation"] = _text(converted.get("pronunciation"))
    converted["validated_by"] = _text(converted.get("validated_by")) or ""
    for key in ("id", "domaine", "sous_domaine", "niveau_indicatif", "equivalent_wo"):
        if key in converted:
            converted[key] = _text(converted[key])
    tests = converted.get("phrases_test") or []
    converted["phrases_test"] = [tests] if isinstance(tests, str) else list(tests)

    # Valide seulement si la source le dit ET qu'il y a une prononciation et un validateur.
    source_status = str((entry.get("wolof") or {}).get("statut") or "").strip().lower()
    is_valid = (
        source_status in _VALIDATED_WORDS
        and converted["pronunciation"]
        and converted["validated_by"]
    )
    converted["statut"] = TermStatus.VALIDATED if is_valid else TermStatus.DRAFT
    if source_status and not is_valid:
        extra["statut_source"] = source_status
    if extra:
        converted["autres"] = extra
    return converted


def convert_source(data: Any, *, version: str | None = None, language: str = "wo") -> Lexicon:
    entries = _entries(data)
    terms = [convert_entry(entry) for entry in entries]
    source_version = data.get("version") if isinstance(data, dict) else None
    try:
        return Lexicon.model_validate(
            {
                "version": version or source_version or "converti",
                "language": language,
                "terms": terms,
            }
        )
    except ValidationError as exc:
        raise LexiconError(f"Conversion impossible :\n{exc}") from exc


def lexicon_to_json(lexicon: Lexicon) -> str:
    """Sérialise le lexique : champs vides omis, sauf le statut, toujours explicite."""

    def clean(term: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in term.items()
            if key == "statut" or value not in (None, "", [], (), {})
        }

    data = lexicon.model_dump(mode="json", by_alias=True)
    data["terms"] = [clean(term) for term in data["terms"]]
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def convert_file(source: Path, destination: Path) -> Lexicon:
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LexiconError(f"Lexique source illisible ({source}) : {exc}") from exc
    lexicon = convert_source(data)
    destination.write_text(lexicon_to_json(lexicon), encoding="utf-8")
    return lexicon
