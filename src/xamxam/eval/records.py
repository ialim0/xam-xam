"""Enregistrements produits par `run` et relus par `report`, avec leurs fichiers CSV."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from xamxam.errors import XamXamError


class Condition(StrEnum):
    """Les trois versions de chaque phrase envoyées au TTS, dans l'ordre des couches."""

    RAW = "brut"  # texte d'origine, symboles compris
    NORMALIZED = "normalise"  # normalisation mathématique seule
    FULL = "lexique"  # normalisation puis réécriture par le lexique

    @property
    def label(self) -> str:
        return _CONDITION_LABELS[self]


_CONDITION_LABELS = {
    Condition.RAW: "Texte brut",
    Condition.NORMALIZED: "Normalisé seul",
    Condition.FULL: "Normalisé + lexique",
}


class RecordsError(XamXamError):
    """Fichier de résultats absent ou invalide."""


@dataclass(frozen=True)
class OutputPaths:
    """Organisation du dossier de sorties."""

    root: Path

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    def audio_file(self, sentence_id: str, condition: Condition) -> Path:
        return self.audio_dir / f"{sentence_id}_{condition}.wav"

    @property
    def transcriptions_csv(self) -> Path:
        return self.root / "stt" / "transcriptions.csv"

    @property
    def terms_csv(self) -> Path:
        return self.root / "stt" / "termes.csv"

    @property
    def human_csv(self) -> Path:
        return self.root / "humain" / "evaluation_humaine.csv"

    @property
    def ranking_csv(self) -> Path:
        return self.root / "rapport" / "classement_termes.csv"

    @property
    def summary_md(self) -> Path:
        return self.root / "rapport" / "resume.md"


@dataclass(frozen=True)
class TranscriptionRecord:
    sentence_id: str
    condition: Condition
    sent_text: str
    transcript: str
    wer: float
    audio_file: str


@dataclass(frozen=True)
class TermRecord:
    sentence_id: str
    condition: Condition
    term: str
    occurrences: int
    errors: int


_TRANSCRIPTION_COLUMNS = (
    "id",
    "condition",
    "texte_envoye",
    "transcription",
    "wer",
    "fichier_audio",
)
_TERM_COLUMNS = ("id", "condition", "terme", "apparitions", "erreurs")


def _write_rows(path: Path, columns: tuple[str, ...], rows: Iterable[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def _read_rows(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise RecordsError(f"{path} introuvable : lancez d'abord `python -m xamxam.eval run`.")
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        missing = set(columns) - set(reader.fieldnames or ())
        if missing:
            raise RecordsError(f"{path} : colonnes manquantes : {', '.join(sorted(missing))}")
        return list(reader)


def write_transcriptions(path: Path, records: Iterable[TranscriptionRecord]) -> None:
    _write_rows(
        path,
        _TRANSCRIPTION_COLUMNS,
        (
            (r.sentence_id, r.condition, r.sent_text, r.transcript, f"{r.wer:.4f}", r.audio_file)
            for r in records
        ),
    )


def read_transcriptions(path: Path) -> list[TranscriptionRecord]:
    try:
        return [
            TranscriptionRecord(
                sentence_id=row["id"],
                condition=Condition(row["condition"]),
                sent_text=row["texte_envoye"],
                transcript=row["transcription"],
                wer=float(row["wer"]),
                audio_file=row["fichier_audio"],
            )
            for row in _read_rows(path, _TRANSCRIPTION_COLUMNS)
        ]
    except ValueError as exc:
        raise RecordsError(f"{path} : valeur invalide ({exc})") from exc


def write_terms(path: Path, records: Iterable[TermRecord]) -> None:
    _write_rows(
        path,
        _TERM_COLUMNS,
        ((r.sentence_id, r.condition, r.term, r.occurrences, r.errors) for r in records),
    )


def read_terms(path: Path) -> list[TermRecord]:
    try:
        return [
            TermRecord(
                sentence_id=row["id"],
                condition=Condition(row["condition"]),
                term=row["terme"],
                occurrences=int(row["apparitions"]),
                errors=int(row["erreurs"]),
            )
            for row in _read_rows(path, _TERM_COLUMNS)
        ]
    except ValueError as exc:
        raise RecordsError(f"{path} : valeur invalide ({exc})") from exc
