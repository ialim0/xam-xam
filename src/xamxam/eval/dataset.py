"""Lecture du jeu de phrases d'évaluation (CSV)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from xamxam.errors import XamXamError

TextColumn = Literal["fr", "wo"]

REQUIRED_COLUMNS = ("id", "notion", "contexte", "fr", "wo", "termes_cibles")
NOTIONS = frozenset({"pythagore", "thales", "concret"})
TERM_SEPARATOR = ";"
# L'identifiant sert à nommer les fichiers audio : on reste sur des caractères sûrs.
_VALID_ID = re.compile(r"^[\w-]+$")


class DatasetError(XamXamError):
    """Le fichier de phrases est invalide."""


@dataclass(frozen=True)
class Sentence:
    id: str
    notion: str
    context: str
    fr: str
    wo: str
    target_terms: tuple[str, ...]

    def text(self, column: TextColumn) -> str:
        return self.fr if column == "fr" else self.wo


def split_terms(raw: str) -> tuple[str, ...]:
    """« a ; b ;; c » → ("a", "b", "c")."""
    return tuple(term.strip() for term in raw.split(TERM_SEPARATOR) if term.strip())


def load_sentences(path: str | Path) -> list[Sentence]:
    path = Path(path)
    try:
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or ())
            if missing:
                raise DatasetError(f"{path} : colonnes manquantes : {', '.join(sorted(missing))}")
            sentences = [_parse_row(row, path, reader.line_num) for row in reader]
    except OSError as exc:
        raise DatasetError(f"Impossible de lire {path} : {exc}") from exc

    ids = [s.id for s in sentences]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise DatasetError(f"{path} : identifiants en double : {', '.join(duplicates)}")
    return sentences


def _parse_row(row: dict[str, str], path: Path, line: int) -> Sentence:
    values = {key: (row.get(key) or "").strip() for key in REQUIRED_COLUMNS}
    where = f"{path}, ligne {line}"
    if not _VALID_ID.match(values["id"]):
        raise DatasetError(f"{where} : identifiant invalide « {values['id']} ».")
    if values["notion"] not in NOTIONS:
        raise DatasetError(
            f"{where} : notion « {values['notion']} » inconnue "
            f"(attendu : {', '.join(sorted(NOTIONS))})."
        )
    if not values["wo"] and not values["fr"]:
        raise DatasetError(f"{where} : les colonnes fr et wo sont vides.")
    return Sentence(
        id=values["id"],
        notion=values["notion"],
        context=values["contexte"],
        fr=values["fr"],
        wo=values["wo"],
        target_terms=split_terms(values["termes_cibles"]),
    )
