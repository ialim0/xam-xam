"""Chargement d'un lexique depuis un fichier JSON."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from xamxam.errors import XamXamError
from xamxam.lexicon.schema import Lexicon


class LexiconError(XamXamError):
    """Le fichier de lexique est introuvable ou invalide."""


def load_lexicon(path: str | Path) -> Lexicon:
    """Charge et valide un lexique JSON (encodé en UTF-8)."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LexiconError(f"Impossible de lire le lexique {path} : {exc}") from exc
    try:
        return Lexicon.model_validate_json(raw)
    except ValidationError as exc:
        raise LexiconError(f"Lexique invalide ({path}) :\n{exc}") from exc
