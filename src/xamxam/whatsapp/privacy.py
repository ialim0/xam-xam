"""Confidentialité : identifiants hachés pour les logs, médias effacés après traitement."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class IdHasher:
    """HMAC-SHA256 tronqué : un numéro de téléphone ne peut pas être retrouvé par force brute
    sans la clé LOG_HASH_KEY, mais un même élève garde le même identifiant dans les logs."""

    def __init__(self, key: str | None) -> None:
        if not key:
            logger.warning(
                "LOG_HASH_KEY absente : clé aléatoire, identifiants non comparables "
                "d'un redémarrage à l'autre."
            )
            key = secrets.token_hex(32)
        self._key = key.encode("utf-8")

    def __repr__(self) -> str:
        return "IdHasher()"

    def __call__(self, value: str) -> str:
        return hmac.new(self._key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


@contextmanager
def media_workspace() -> Iterator[Path]:
    """Dossier temporaire pour les médias d'un traitement, supprimé quoi qu'il arrive."""
    with tempfile.TemporaryDirectory(prefix="xamxam-") as directory:
        yield Path(directory)
