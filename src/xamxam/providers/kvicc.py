"""Fournisseurs TTS et STT de l'API Kiriku, mise à disposition par les organisateurs du KVICC.

Contrat (API compatible OpenAI, documentation sur <hôte>/docs) :
- TTS : POST /v1/audio/speech, JSON {model: "kiriku-tts", input, voice, speed?, pitch?}
  → WAV 22,05 kHz. Voix : wolof, pulaar (pas de sérère).
- STT : POST /v1/audio/transcriptions, multipart {file, model: "m-kiriku-asr", language,
  response_format} → {"text": "..."}. Langues : wolof, pulaar, sérère.
- Authentification : en-tête « Authorization: Bearer sk-kiriku-... ».
- Limites par clé : 30 requêtes par minute, 512 caractères par synthèse, 60 s par transcription.
  Au-delà, 429 (ou 503 si le serveur est saturé) avec un en-tête Retry-After.

KVICC_TTS_URL et KVICC_STT_URL contiennent l'URL complète de chaque route.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from xamxam import __version__
from xamxam.config import Settings
from xamxam.metrics import record_request
from xamxam.providers.audio import concat_wav
from xamxam.providers.base import (
    ProviderError,
    ProviderNotConfiguredError,
    STTProvider,
    TTSProvider,
)
from xamxam.providers.chunking import split_text
from xamxam.providers.ratelimit import RateLimiter

TTS_MODEL = "kiriku-tts"
STT_MODEL = "m-kiriku-asr"
MAX_TTS_CHARS = 512
REQUESTS_PER_MINUTE = 30

# Codes de langue Xam-Xam → valeurs attendues par l'API.
TTS_VOICES = {"wo": "wolof", "ff": "pulaar"}
STT_LANGUAGES = {"wo": "wolof", "ff": "pulaar", "srr": "serer"}

_RETRYABLE_STATUSES = frozenset({429, 503})
_DEFAULT_RETRY_AFTER = 2.0
_MAX_RETRY_AFTER = 60.0


class KviccClient:
    """Client HTTP de l'API : authentification, limitation du débit, nouvelles tentatives.

    Le TTS et le STT consomment le même quota (une clé par équipe) : ils doivent partager
    un même limiteur (`limiter`) pour que la limitation du débit soit globale.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
        min_interval: float = 60.0 / REQUESTS_PER_MINUTE,
        limiter: RateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ProviderNotConfiguredError("KVICC_API_KEY est vide.")
        self._http = httpx.Client(
            timeout=timeout,
            transport=transport,
            # Le proxy d'hébergement bloque les requêtes sans User-Agent.
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": f"xamxam/{__version__}"},
        )
        self._max_retries = max_retries
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(
            60.0 / min_interval if min_interval > 0 else 0, clock=clock, sleep=sleep
        )
        self.request_count = 0

    def __repr__(self) -> str:
        return f"KviccClient(interval={self._limiter.interval})"

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    def close(self) -> None:
        self._http.close()

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST avec respect du débit et nouvelles tentatives sur 429 / 503."""
        attempt = 0
        while True:
            # Espace les requêtes pour rester sous la limite au lieu de subir des 429.
            self._limiter.acquire()
            self.request_count += 1
            record_request("kiriku")
            try:
                response = self._http.post(url, **kwargs)
            except httpx.HTTPError as exc:
                raise ProviderError(f"API KVICC injoignable ({url}) : {exc}") from exc
            if response.status_code in _RETRYABLE_STATUSES and attempt < self._max_retries:
                attempt += 1
                self._sleep(_retry_after(response))
                continue
            if response.is_error:
                raise ProviderError(_error_message(response))
            return response


def _retry_after(response: httpx.Response) -> float:
    try:
        delay = float(response.headers.get("Retry-After", _DEFAULT_RETRY_AFTER))
    except ValueError:
        delay = _DEFAULT_RETRY_AFTER
    return min(max(delay, 0.0), _MAX_RETRY_AFTER)


def _error_message(response: httpx.Response) -> str:
    """Extrait le message d'une erreur au format OpenAI : {"error": {"message": ...}}."""
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:300]
    hint = " Vérifiez KVICC_API_KEY." if response.status_code == 401 else ""
    return f"API KVICC : erreur {response.status_code} : {message}{hint}"


def _audio_upload(audio: bytes) -> tuple[str, bytes, str]:
    """Nom et type MIME du fichier envoyé au STT, déduits de la signature du contenu."""
    if audio[:4] == b"OggS":
        return ("audio.ogg", audio, "audio/ogg")
    return ("audio.wav", audio, "audio/wav")


def _require(value: str | None, message: str) -> str:
    if not value:
        raise ProviderNotConfiguredError(message)
    return value


def client_from_settings(settings: Settings, *, limiter: RateLimiter | None = None) -> KviccClient:
    return KviccClient(
        _require(settings.kvicc_api_key, "KVICC_API_KEY n'est pas définie."), limiter=limiter
    )


class KviccTTSProvider(TTSProvider):
    """Synthèse vocale Kiriku. Les textes de plus de 512 caractères sont découpés par
    phrase, synthétisés séparément puis réassemblés en un seul WAV."""

    name = "kvicc"

    def __init__(
        self,
        url: str,
        client: KviccClient,
        *,
        speed: float | None = None,
        pitch: float | None = None,
    ) -> None:
        self._url = url
        self._client = client
        # None : valeur par défaut du serveur (1,2 pour le wolof, 1,0 pour le pulaar).
        self._speed = speed
        self._pitch = pitch

    @classmethod
    def from_settings(
        cls, settings: Settings, client: KviccClient | None = None
    ) -> KviccTTSProvider:
        url = _require(
            settings.kvicc_tts_url, "TTS KVICC non configuré : définissez KVICC_TTS_URL."
        )
        return cls(url, client or client_from_settings(settings))

    def __repr__(self) -> str:
        return f"KviccTTSProvider(url={self._url!r})"

    @property
    def cache_identity(self) -> str:
        # L'URL est volontairement exclue : elle change d'un déploiement à l'autre.
        return f"kvicc:{TTS_MODEL}:speed={self._speed}:pitch={self._pitch}"

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        voice = TTS_VOICES.get(language)
        if voice is None:
            raise ProviderError(
                f"Pas de voix KVICC pour la langue « {language} » "
                f"(disponibles : {', '.join(TTS_VOICES)})."
            )
        chunks = split_text(text, MAX_TTS_CHARS)
        if not chunks:
            raise ProviderError("Texte vide : rien à synthétiser.")
        return concat_wav([self._synthesize_chunk(chunk, voice) for chunk in chunks])

    def _synthesize_chunk(self, text: str, voice: str) -> bytes:
        payload: dict[str, Any] = {
            "model": TTS_MODEL,
            "input": text,
            "voice": voice,
            "response_format": "wav",
        }
        if self._speed is not None:
            payload["speed"] = self._speed
        if self._pitch is not None:
            payload["pitch"] = self._pitch
        return self._client.post(self._url, json=payload).content


class KviccSTTProvider(STTProvider):
    """Reconnaissance vocale Kiriku (M-Kiriku-ASR, 60 s d'audio au plus par requête)."""

    name = "kvicc"

    def __init__(self, url: str, client: KviccClient) -> None:
        self._url = url
        self._client = client

    @classmethod
    def from_settings(
        cls, settings: Settings, client: KviccClient | None = None
    ) -> KviccSTTProvider:
        url = _require(
            settings.kvicc_stt_url, "STT KVICC non configuré : définissez KVICC_STT_URL."
        )
        return cls(url, client or client_from_settings(settings))

    def __repr__(self) -> str:
        return f"KviccSTTProvider(url={self._url!r})"

    @property
    def cache_identity(self) -> str:
        return f"kvicc:{STT_MODEL}"

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        api_language = STT_LANGUAGES.get(language)
        if api_language is None:
            raise ProviderError(
                f"Langue « {language} » non reconnue par le STT KVICC "
                f"(disponibles : {', '.join(STT_LANGUAGES)})."
            )
        response = self._client.post(
            self._url,
            files={"file": _audio_upload(audio)},
            data={"model": STT_MODEL, "language": api_language, "response_format": "json"},
        )
        try:
            return str(response.json()["text"]).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"Réponse STT KVICC inattendue : {response.text[:300]}") from exc
