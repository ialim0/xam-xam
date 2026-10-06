"""Client TimaLens : créer un clip à partir d'un script wolof, suivre son statut, obtenir le lien.

La clé est lue dans TIMALENS_API_KEY. Sans clé, la vidéo est simplement désactivée :
build_timalens_client() retourne None et le reste de Xam-Xam fonctionne normalement.

Squelette : les endpoints de l'API TimaLens ne sont pas encore renseignés.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from xamxam.config import Settings
from xamxam.errors import XamXamError

logger = logging.getLogger(__name__)

VIDEO_DISABLED_MESSAGE = (
    "Génération vidéo désactivée : TIMALENS_API_KEY n'est pas définie. "
    "Clé gratuite pour les participants du KVICC sur demande."
)

_NOT_IMPLEMENTED = (
    "Les endpoints de l'API TimaLens ne sont pas encore intégrés : "
    "complétez xamxam/timalens/client.py à partir de la documentation TimaLens."
)


class TimaLensDisabledError(XamXamError):
    """La génération vidéo est demandée alors qu'aucune clé n'est configurée."""


class ClipStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class ClipJob:
    clip_id: str
    status: ClipStatus


class TimaLensClient:
    """Accès à l'API TimaLens."""

    def __init__(self, api_key: str, *, base_url: str | None = None, timeout: float = 60.0) -> None:
        if not api_key:
            raise TimaLensDisabledError(VIDEO_DISABLED_MESSAGE)
        self._api_key = api_key
        # TODO(TimaLens) : URL de base de l'API à renseigner.
        self._base_url = base_url
        self._timeout = timeout

    def __repr__(self) -> str:
        # Ne jamais afficher la clé.
        return f"TimaLensClient(base_url={self._base_url!r})"

    def create_clip(self, script: str, *, language: str = "wo") -> ClipJob:
        """Lance la génération d'un clip explicatif à partir d'un script."""
        if not script.strip():
            raise ValueError("Le script du clip est vide.")
        # TODO(TimaLens) : requête de création (chemin, authentification avec self._api_key,
        # format du script et de la langue), puis conversion de la réponse en ClipJob.
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_status(self, clip_id: str) -> ClipStatus:
        """Retourne l'état de génération d'un clip."""
        # TODO(TimaLens) : requête de statut et correspondance avec ClipStatus.
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_link(self, clip_id: str) -> str:
        """Retourne le lien du clip une fois prêt."""
        # TODO(TimaLens) : requête du lien ; lever une erreur claire si le clip n'est pas prêt.
        raise NotImplementedError(_NOT_IMPLEMENTED)


def build_timalens_client(settings: Settings) -> TimaLensClient | None:
    """Retourne un client si la clé est configurée, sinon None (vidéo désactivée)."""
    if not settings.timalens_api_key:
        logger.info(VIDEO_DISABLED_MESSAGE)
        return None
    return TimaLensClient(settings.timalens_api_key)
