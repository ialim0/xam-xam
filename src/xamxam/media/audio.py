"""Conversions audio avec ffmpeg (dépendance système, installée dans l'image Docker et la CI).

- WAV (sortie du TTS Kiriku) → OGG Opus : seul format affiché comme note vocale par WhatsApp.
- Durée d'un audio, et découpage en morceaux : le STT Kiriku accepte 60 s au plus par requête.
Le STT accepte directement l'OGG Opus des notes vocales : aucune conversion n'est nécessaire
pour les notes de 60 s ou moins.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from xamxam.errors import XamXamError

_TIMEOUT_SECONDS = 120


class AudioError(XamXamError):
    """ffmpeg absent, ou audio illisible."""


def _binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise AudioError(f"{name} est introuvable : installez ffmpeg (voir README.md).")
    return path


def _run(command: list[str], *, stdin: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            command, input=stdin, capture_output=True, check=False, timeout=_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"{Path(command[0]).name} a dépassé {_TIMEOUT_SECONDS} s.") from exc
    if result.returncode != 0:
        # Seule la fin de stderr est gardée : elle décrit l'erreur sans contenu utilisateur.
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]
        raise AudioError(f"{Path(command[0]).name} a échoué : {' '.join(detail)}")
    return result.stdout


def audio_duration(path: Path) -> float:
    """Durée d'un fichier audio en secondes."""
    output = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        return float(output.decode().strip())
    except ValueError as exc:
        raise AudioError("Durée de l'audio illisible.") from exc


def split_audio(path: Path, output_dir: Path, *, chunk_seconds: float) -> list[Path]:
    """Découpe un audio en morceaux WAV 16 kHz mono de `chunk_seconds` au plus.

    Le WAV 16 kHz mono est le format que le STT utilise en interne : pas de perte inutile.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "morceau_%03d.wav"
    _run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(pattern),
        ]
    )
    return sorted(output_dir.glob("morceau_*.wav"))


def wav_to_ogg_opus(wav: bytes) -> bytes:
    """Convertit un WAV en OGG Opus mono, sans fichier intermédiaire."""
    return _run(
        [
            _binary("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-f",
            "wav",
            "-i",
            "pipe:0",
            "-ac",
            "1",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-f",
            "ogg",
            "pipe:1",
        ],
        stdin=wav,
    )
