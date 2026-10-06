"""Fournisseurs factices, déterministes et hors ligne, pour les tests et le développement.

Le TTS mock produit un WAV silencieux valide qui embarque le texte dans un chunk RIFF
dédié ; le STT mock relit ce chunk. Un aller-retour rend donc le texte d'origine,
éventuellement modifié par une fonction `transform` pour simuler des erreurs.
"""

from __future__ import annotations

import io
import struct
import wave
from collections.abc import Callable

from xamxam.providers.base import ProviderError, STTProvider, TTSProvider

_TEXT_CHUNK_ID = b"xmxt"


def _append_chunk(wav: bytes, chunk_id: bytes, payload: bytes) -> bytes:
    """Ajoute un chunk à un fichier RIFF et met à jour la taille globale."""
    chunk = chunk_id + struct.pack("<I", len(payload)) + payload
    if len(payload) % 2:
        chunk += b"\x00"  # les chunks RIFF sont alignés sur 2 octets
    body = wav[8:] + chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _read_chunk(wav: bytes, chunk_id: bytes) -> bytes | None:
    """Retourne le contenu du premier chunk `chunk_id`, ou None s'il est absent."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        return None
    offset = 12
    while offset + 8 <= len(wav):
        current_id = wav[offset : offset + 4]
        (size,) = struct.unpack("<I", wav[offset + 4 : offset + 8])
        start = offset + 8
        if current_id == chunk_id:
            return wav[start : start + size]
        offset = start + size + (size % 2)
    return None


class MockTTSProvider(TTSProvider):
    """WAV silencieux, mono 16 bits, dont la durée suit la longueur du texte."""

    name = "mock"

    def __init__(self, *, sample_rate: int = 16_000, seconds_per_char: float = 0.01) -> None:
        self._sample_rate = sample_rate
        self._seconds_per_char = seconds_per_char

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        frames = max(1, int(len(text) * self._seconds_per_char * self._sample_rate))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(b"\x00\x00" * frames)
        return _append_chunk(buffer.getvalue(), _TEXT_CHUNK_ID, text.encode("utf-8"))


class MockSTTProvider(STTProvider):
    """Relit le texte embarqué par MockTTSProvider, puis applique `transform`."""

    name = "mock"

    def __init__(self, transform: Callable[[str], str] | None = None) -> None:
        self._transform = transform or (lambda text: text)

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        payload = _read_chunk(audio, _TEXT_CHUNK_ID)
        if payload is None:
            raise ProviderError("Audio non reconnu : il n'a pas été produit par MockTTSProvider.")
        return self._transform(payload.decode("utf-8"))
