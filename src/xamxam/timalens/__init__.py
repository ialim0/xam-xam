"""Client de l'API TimaLens (service propriétaire, optionnel) : vidéos explicatives narrées."""

from xamxam.timalens.client import (
    VIDEO_DISABLED_MESSAGE,
    JobStatus,
    Narration,
    RenderQuote,
    RenderRefusedError,
    TimaLensClient,
    TimaLensDisabledError,
    TimaLensError,
    build_timalens_client,
)

__all__ = [
    "VIDEO_DISABLED_MESSAGE",
    "JobStatus",
    "Narration",
    "RenderQuote",
    "RenderRefusedError",
    "TimaLensClient",
    "TimaLensDisabledError",
    "TimaLensError",
    "build_timalens_client",
]
