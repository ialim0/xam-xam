"""Évaluation humaine sans afficher les conditions ni les textes envoyés au TTS."""

from __future__ import annotations

import csv
import hashlib
import random
import secrets
import shutil
from pathlib import Path

from xamxam.eval.human import HUMAN_COLUMNS, HumanEvalError, load_human_ratings
from xamxam.eval.records import Condition, OutputPaths, read_transcriptions

BLIND_COLUMNS = (
    "echantillon",
    "fichier_audio",
    "texte_de_reference",
    "note_correction_wolof",
    "note_prononciation_termes",
    "mots_mal_prononces",
    "commentaire",
)
MAP_COLUMNS = ("echantillon", "id", "condition", "sha256_audio")


def _audio_hash(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _read_csv(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        raise HumanEvalError(f"{path} introuvable.")
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if not set(columns) <= set(reader.fieldnames or ()):
            raise HumanEvalError(f"{path} : colonnes attendues : {', '.join(columns)}.")
        return list(reader)


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def create_blind_sheet(
    paths: OutputPaths, *, seed: int | None = None, overwrite: bool = False
) -> int:
    """Copie les audios sous des noms opaques ; la correspondance reste à l'organisateur."""
    if (paths.blind_csv.exists() or paths.blind_map_csv.exists()) and not overwrite:
        raise HumanEvalError(
            "Fiche aveugle déjà présente : utilisez --overwrite-blind pour la recréer."
        )
    records = read_transcriptions(paths.transcriptions_csv)
    if not records:
        raise HumanEvalError("Aucun audio à évaluer.")
    shuffled = records.copy()
    random.Random(seed if seed is not None else secrets.randbits(64)).shuffle(shuffled)
    references = {
        record.sentence_id: record.sent_text
        for record in records
        if record.condition is Condition.RAW
    }
    audio_dir = paths.blind_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sheet_rows: list[tuple[str, ...]] = []
    map_rows: list[tuple[str, ...]] = []
    for position, record in enumerate(shuffled, start=1):
        sample = f"S{position:04d}"
        source = paths.root / record.audio_file
        if not source.is_file():
            raise HumanEvalError(f"Audio introuvable : {source}.")
        target = audio_dir / f"{sample}{source.suffix}"
        shutil.copyfile(source, target)
        sheet_rows.append(
            (sample, f"audio/{target.name}", references[record.sentence_id], "", "", "", "")
        )
        map_rows.append((sample, record.sentence_id, str(record.condition), _audio_hash(source)))
    _write_csv(paths.blind_csv, BLIND_COLUMNS, sheet_rows)
    _write_csv(paths.blind_map_csv, MAP_COLUMNS, map_rows)
    return len(shuffled)


def import_blind_sheet(paths: OutputPaths, *, overwrite_human: bool = False) -> int:
    """Valide les notes aveugles puis les réintègre à la fiche utilisée par le rapport."""
    if paths.human_csv.exists() and load_human_ratings(paths.human_csv) and not overwrite_human:
        raise HumanEvalError(
            "La fiche humaine contient déjà des notes : "
            "utilisez --overwrite-human pour la remplacer."
        )
    mapping_rows = _read_csv(paths.blind_map_csv, MAP_COLUMNS)
    blind_rows = _read_csv(paths.blind_csv, BLIND_COLUMNS)
    mapping = {
        row["echantillon"]: (row["id"], row["condition"], row["sha256_audio"])
        for row in mapping_rows
    }
    if len(mapping) != len(mapping_rows):
        raise HumanEvalError("Correspondance aveugle : échantillon en double.")
    by_key = {
        (record.sentence_id, str(record.condition)): record
        for record in read_transcriptions(paths.transcriptions_csv)
    }
    mapped_keys = {(sentence_id, condition) for sentence_id, condition, _ in mapping.values()}
    if len(mapping) != len(by_key) or mapped_keys != set(by_key):
        raise HumanEvalError("Correspondance aveugle incomplète pour ce run.")
    seen: set[str] = set()
    human_rows: list[tuple[str, ...]] = []
    for row in blind_rows:
        sample = row["echantillon"]
        if sample in seen or sample not in mapping:
            raise HumanEvalError(f"Échantillon inconnu ou en double : {sample}.")
        if row["fichier_audio"] != f"audio/{sample}.wav":
            raise HumanEvalError(f"Fichier audio incohérent pour {sample}.")
        seen.add(sample)
        sentence_id, condition, expected_hash = mapping[sample]
        try:
            key = (sentence_id, str(Condition(condition)))
            record = by_key[key]
        except (ValueError, KeyError):
            raise HumanEvalError(f"Correspondance invalide : {sample}.") from None
        blind_audio = paths.blind_dir / row["fichier_audio"]
        source_audio = paths.root / record.audio_file
        if not blind_audio.is_file() or not source_audio.is_file():
            raise HumanEvalError(f"Audio introuvable pour {sample}.")
        if _audio_hash(blind_audio) != expected_hash or _audio_hash(source_audio) != expected_hash:
            raise HumanEvalError(f"Audio modifié depuis la création de la fiche : {sample}.")
        human_rows.append(
            (
                sentence_id,
                condition,
                record.sent_text,
                record.audio_file,
                row["note_correction_wolof"],
                row["note_prononciation_termes"],
                row["mots_mal_prononces"],
                row["commentaire"],
            )
        )
    if seen != set(mapping):
        raise HumanEvalError("Fiche aveugle incomplète.")
    temporary = paths.human_csv.with_suffix(".validation.tmp")
    try:
        _write_csv(temporary, HUMAN_COLUMNS, human_rows)
        ratings = load_human_ratings(temporary)
        temporary.replace(paths.human_csv)
    finally:
        temporary.unlink(missing_ok=True)
    return len(ratings)
