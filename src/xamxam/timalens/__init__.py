"""Client minimal de l'API TimaLens (service propriétaire, optionnel) pour les clips vidéo."""

from xamxam.timalens.client import (
    VIDEO_DISABLED_MESSAGE,
    ClipJob,
    ClipStatus,
    TimaLensClient,
    TimaLensDisabledError,
    build_timalens_client,
)

__all__ = [
    "VIDEO_DISABLED_MESSAGE",
    "ClipJob",
    "ClipStatus",
    "TimaLensClient",
    "TimaLensDisabledError",
    "build_timalens_client",
]
