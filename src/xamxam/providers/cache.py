"""Caches disque des audios TTS et des transcriptions STT, indexés par empreinte SHA-256.

En développement, ils vivent dans .cache/ ; en production, sur un bucket Cloud Storage
monté comme volume, pour survivre aux redémarrages.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from pathlib import Path

from xamxam.metrics import record_cache
from xamxam.providers.base import STTProvider, TTSProvider

logger = logging.getLogger(__name__)


class DiskCache:
    """Stockage clé → octets, un fichier par entrée, écriture atomique."""

    def __init__(self, directory: Path, suffix: str, *, name: str) -> None:
        self._directory = directory
        self._suffix = suffix
        self._name = name
        self.hits = 0
        self.misses = 0

    @property
    def directory(self) -> Path:
        return self._directory

    def path(self, key: str) -> Path:
        # Sous-dossier par préfixe pour éviter des milliers de fichiers dans un même dossier.
        return self._directory / key[:2] / f"{key}{self._suffix}"

    def get(self, key: str) -> bytes | None:
        path = self.path(key)
        if path.is_file():
            self.hits += 1
            record_cache(self._name, hit=True)
            return path.read_bytes()
        self.misses += 1
        record_cache(self._name, hit=False)
        return None

    def put(self, key: str, value: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Écriture atomique : un arrêt brutal ne laisse jamais une entrée tronquée.
        temporary = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            temporary.write_bytes(value)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def fingerprint(*parts: str | bytes) -> str:
    """Empreinte SHA-256 d'une suite de chaînes et d'octets, sans ambiguïté de concaténation."""
    digest = hashlib.sha256()
    for part in parts:
        data = part.encode("utf-8") if isinstance(part, str) else part
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


class CachedTTSProvider(TTSProvider):
    """Enveloppe un TTS pour ne jamais régénérer un audio déjà produit.

    La clé est l'empreinte de (identité du fournisseur, langue, texte exact) :
    changer de modèle, de vitesse ou d'un seul caractère produit une nouvelle entrée.
    """

    def __init__(self, inner: TTSProvider, cache_dir: Path) -> None:
        self._inner = inner
        self._cache = DiskCache(cache_dir, ".wav", name="tts")
        self.name = inner.name

    def __repr__(self) -> str:
        return f"CachedTTSProvider({self._inner!r}, cache_dir={str(self._cache.directory)!r})"

    @property
    def hits(self) -> int:
        return self._cache.hits

    @property
    def misses(self) -> int:
        return self._cache.misses

    @property
    def cache_identity(self) -> str:
        return self._inner.cache_identity

    def cache_key(self, text: str, language: str) -> str:
        material = json.dumps([self._inner.cache_identity, language, text], ensure_ascii=False)
        return fingerprint(material)

    def cache_path(self, text: str, language: str) -> Path:
        return self._cache.path(self.cache_key(text, language))

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        key = self.cache_key(text, language)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        audio = self._inner.synthesize(text, language=language)
        self._cache.put(key, audio)
        return audio


class CachedSTTProvider(STTProvider):
    """Enveloppe un STT : une transcription est stockée sous l'empreinte de
    (identité du fournisseur, langue, contenu exact de l'audio)."""

    def __init__(self, inner: STTProvider, cache_dir: Path) -> None:
        self._inner = inner
        self._cache = DiskCache(cache_dir, ".txt", name="stt")
        self.name = inner.name

    def __repr__(self) -> str:
        return f"CachedSTTProvider({self._inner!r}, cache_dir={str(self._cache.directory)!r})"

    @property
    def hits(self) -> int:
        return self._cache.hits

    @property
    def misses(self) -> int:
        return self._cache.misses

    @property
    def cache_identity(self) -> str:
        return self._inner.cache_identity

    def cache_key(self, audio: bytes, language: str) -> str:
        return fingerprint(self._inner.cache_identity, language, audio)

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        key = self.cache_key(audio, language)
        cached = self._cache.get(key)
        if cached is not None:
            return cached.decode("utf-8")
        text = self._inner.transcribe(audio, language=language)
        self._cache.put(key, text.encode("utf-8"))
        return text
