"""Fournisseurs TTS et STT des organisateurs du KVICC.

Squelette volontairement incomplet : la documentation de l'API n'est pas encore connue.
Aucun endpoint, en-tête ou format n'est supposé ici.
"""

from __future__ import annotations

from xamxam.config import Settings
from xamxam.providers.base import ProviderNotConfiguredError, STTProvider, TTSProvider

_NOT_IMPLEMENTED = (
    "L'API KVICC n'est pas encore intégrée : complétez xamxam/providers/kvicc.py "
    "dès que la documentation des organisateurs est disponible. "
    "En attendant, utilisez --provider mock."
)


class KviccTTSProvider(TTSProvider):
    """TTS des organisateurs du KVICC."""

    name = "kvicc"

    def __init__(self, url: str, api_key: str, *, timeout: float = 30.0) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> KviccTTSProvider:
        if not (settings.kvicc_tts_url and settings.kvicc_api_key):
            raise ProviderNotConfiguredError(
                "TTS KVICC non configuré : définissez KVICC_TTS_URL et KVICC_API_KEY."
            )
        return cls(settings.kvicc_tts_url, settings.kvicc_api_key)

    def __repr__(self) -> str:
        return f"KviccTTSProvider(url={self._url!r})"

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        # TODO(KVICC) : à compléter avec la documentation officielle :
        #   - méthode HTTP et chemin exact (KVICC_TTS_URL est-elle l'URL complète ?) ;
        #   - mode d'authentification (en-tête, paramètre…) avec KVICC_API_KEY ;
        #   - format de la requête (texte, code langue, voix, vitesse…) ;
        #   - format de la réponse (WAV direct, autre format à convertir, JSON + URL…) ;
        #   - codes d'erreur, limites de débit et taille maximale du texte.
        # Utiliser httpx.Client(timeout=self._timeout) et lever ProviderError en cas d'échec.
        raise NotImplementedError(_NOT_IMPLEMENTED)


class KviccSTTProvider(STTProvider):
    """STT des organisateurs du KVICC."""

    name = "kvicc"

    def __init__(self, url: str, api_key: str, *, timeout: float = 60.0) -> None:
        self._url = url
        self._api_key = api_key
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> KviccSTTProvider:
        if not (settings.kvicc_stt_url and settings.kvicc_api_key):
            raise ProviderNotConfiguredError(
                "STT KVICC non configuré : définissez KVICC_STT_URL et KVICC_API_KEY."
            )
        return cls(settings.kvicc_stt_url, settings.kvicc_api_key)

    def __repr__(self) -> str:
        return f"KviccSTTProvider(url={self._url!r})"

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        # TODO(KVICC) : à compléter avec la documentation officielle :
        #   - méthode HTTP, chemin et authentification ;
        #   - envoi de l'audio (multipart, binaire brut, base64…) et formats acceptés ;
        #   - format de la réponse (texte seul, segments horodatés, score de confiance…).
        raise NotImplementedError(_NOT_IMPLEMENTED)
