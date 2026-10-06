"""Vérification de l'en-tête X-Hub-Signature-256 envoyé par Meta."""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-Hub-Signature-256"
_PREFIX = "sha256="


def compute_signature(body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return _PREFIX + digest


def is_valid_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    """Vrai si l'en-tête correspond au HMAC-SHA256 du corps brut (comparaison à temps constant)."""
    if not header or not header.startswith(_PREFIX) or not app_secret:
        return False
    return hmac.compare_digest(header, compute_signature(body, app_secret))
