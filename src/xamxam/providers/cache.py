"""Cache disque des audios TTS, indexé par l'empreinte du texte."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from xamxam.providers.base import TTSProvider

logger = logging.getLogger(__name__)


class CachedTTSProvider(TTSProvider):
    """Enveloppe un TTS pour ne jamais régénérer un audio déjà produit.

    La clé est l'empreinte SHA-256 de (identité du fournisseur, langue, texte exact) :
    changer de modèle, de vitesse ou d'un seul caractère produit une nouvelle entrée.
    """

    def __init__(self, inner: TTSProvider, cache_dir: Path) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self.name = inner.name
        self.hits = 0
        self.misses = 0

    def __repr__(self) -> str:
        return f"CachedTTSProvider({self._inner!r}, cache_dir={str(self._cache_dir)!r})"

    @property
    def cache_identity(self) -> str:
        return self._inner.cache_identity

    def cache_key(self, text: str, language: str) -> str:
        material = json.dumps([self._inner.cache_identity, language, text], ensure_ascii=False)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def cache_path(self, text: str, language: str) -> Path:
        key = self.cache_key(text, language)
        # Sous-dossier par préfixe pour éviter des milliers de fichiers dans un même dossier.
        return self._cache_dir / key[:2] / f"{key}.wav"

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        path = self.cache_path(text, language)
        if path.is_file():
            self.hits += 1
            return path.read_bytes()
        audio = self._inner.synthesize(text, language=language)
        self.misses += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        # Écriture atomique : un arrêt brutal ne laisse jamais un WAV tronqué dans le cache.
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(audio)
        temporary.replace(path)
        return audio
