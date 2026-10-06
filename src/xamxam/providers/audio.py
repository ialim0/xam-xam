"""Outils audio : assemblage de plusieurs fichiers WAV."""

from __future__ import annotations

import io
import wave
from collections.abc import Sequence

from xamxam.providers.base import ProviderError


def concat_wav(clips: Sequence[bytes]) -> bytes:
    """Concatène des WAV PCM ayant le même format (canaux, échantillonnage, résolution)."""
    if not clips:
        raise ValueError("Aucun audio à assembler.")
    if len(clips) == 1:
        return clips[0]
    params: tuple[int, int, int] | None = None
    frames: list[bytes] = []
    try:
        for clip in clips:
            with wave.open(io.BytesIO(clip), "rb") as wav:
                current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                if params is not None and current != params:
                    raise ProviderError("Impossible d'assembler des WAV de formats différents.")
                params = current
                frames.append(wav.readframes(wav.getnframes()))
    except (wave.Error, EOFError) as exc:
        raise ProviderError(f"WAV illisible lors de l'assemblage : {exc}") from exc

    channels, sample_width, frame_rate = params
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sample_width)
        out.setframerate(frame_rate)
        out.writeframes(b"".join(frames))
    return buffer.getvalue()
