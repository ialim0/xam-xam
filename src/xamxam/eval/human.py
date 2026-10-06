"""Étape 3 : fiche d'évaluation humaine à remplir, et relecture des notes."""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from xamxam.errors import XamXamError
from xamxam.eval.dataset import split_terms
from xamxam.eval.records import Condition, TranscriptionRecord
from xamxam.lexicon import normalize_form

logger = logging.getLogger(__name__)

HUMAN_COLUMNS = (
    "id",
    "condition",
    "texte_envoye",
    "fichier_audio",
    "note_correction_wolof",
    "note_prononciation_termes",
    "mots_mal_prononces",
    "commentaire",
)
MIN_SCORE, MAX_SCORE = 1, 5


class HumanEvalError(XamXamError):
    """Fiche d'évaluation humaine mal remplie."""


@dataclass(frozen=True)
class HumanRating:
    sentence_id: str
    condition: Condition
    wolof_score: int | None
    pronunciation_score: int | None
    mispronounced: tuple[str, ...]

    def mentions(self, term: str) -> int:
        """Nombre de fois où l'évaluateur a signalé ce terme comme mal prononcé."""
        key = normalize_form(term)
        return sum(1 for word in self.mispronounced if normalize_form(word) == key)


def write_human_template(
    transcriptions: Iterable[TranscriptionRecord], path: Path, *, overwrite: bool = False
) -> bool:
    """Écrit la fiche vierge. Une fiche existante n'est jamais écrasée sans `overwrite`,
    pour ne pas perdre des annotations déjà saisies. Retourne True si le fichier a été écrit."""
    if path.exists() and not overwrite:
        logger.warning(
            "%s existe déjà : conservé (utilisez --overwrite-human pour le recréer).", path
        )
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(HUMAN_COLUMNS)
        for record in transcriptions:
            writer.writerow(
                (
                    record.sentence_id,
                    record.condition,
                    record.sent_text,
                    record.audio_file,
                    "",
                    "",
                    "",
                    "",
                )
            )
    return True


def _parse_score(raw: str, column: str, where: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        score = int(raw)
    except ValueError:
        raise HumanEvalError(f"{where} : {column} doit être un entier, reçu « {raw} ».") from None
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise HumanEvalError(f"{where} : {column} doit être entre {MIN_SCORE} et {MAX_SCORE}.")
    return score


def load_human_ratings(path: Path) -> list[HumanRating]:
    """Relit la fiche. Les lignes non remplies sont ignorées ; fichier absent → liste vide."""
    if not path.exists():
        logger.info("Pas de fiche d'évaluation humaine (%s) : rapport basé sur le STT seul.", path)
        return []
    ratings = []
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            where = f"{path}, ligne {reader.line_num}"
            wolof = _parse_score(
                row.get("note_correction_wolof") or "", "note_correction_wolof", where
            )
            pron = _parse_score(
                row.get("note_prononciation_termes") or "", "note_prononciation_termes", where
            )
            words = split_terms(row.get("mots_mal_prononces") or "")
            if wolof is None and pron is None and not words:
                continue
            try:
                condition = Condition(row.get("condition", ""))
            except ValueError:
                raise HumanEvalError(
                    f"{where} : condition inconnue « {row.get('condition')} »."
                ) from None
            ratings.append(HumanRating(row.get("id", ""), condition, wolof, pron, words))
    return ratings
