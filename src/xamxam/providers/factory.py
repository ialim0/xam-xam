"""Choix du fournisseur TTS / STT selon la configuration."""

from __future__ import annotations

import logging
from enum import StrEnum

from xamxam.config import Settings
from xamxam.providers.base import ProviderNotConfiguredError, STTProvider, TTSProvider
from xamxam.providers.kvicc import KviccSTTProvider, KviccTTSProvider, client_from_settings
from xamxam.providers.mock import MockSTTProvider, MockTTSProvider
from xamxam.providers.ratelimit import RateLimiter

logger = logging.getLogger(__name__)


class ProviderName(StrEnum):
    AUTO = "auto"  # KVICC si configuré, sinon mock
    MOCK = "mock"
    KVICC = "kvicc"


def _use_kvicc(name: ProviderName, configured: bool, kind: str) -> bool:
    if name is ProviderName.KVICC:
        return True
    if name is ProviderName.AUTO and not configured:
        logger.info("%s KVICC non configuré : utilisation du %s mock.", kind, kind)
    return name is ProviderName.AUTO and configured


def create_tts_provider(name: ProviderName, settings: Settings) -> TTSProvider:
    if _use_kvicc(name, settings.kvicc_tts_configured, "TTS"):
        return KviccTTSProvider.from_settings(settings)
    return MockTTSProvider()


def create_stt_provider(name: ProviderName, settings: Settings) -> STTProvider:
    if _use_kvicc(name, settings.kvicc_stt_configured, "STT"):
        return KviccSTTProvider.from_settings(settings)
    return MockSTTProvider()


def create_providers(
    name: ProviderName, settings: Settings, *, limiter: RateLimiter | None = None
) -> tuple[TTSProvider, STTProvider]:
    """Crée le couple TTS / STT. Avec KVICC, les deux partagent un client, donc un quota."""
    use_tts = _use_kvicc(name, settings.kvicc_tts_configured, "TTS")
    use_stt = _use_kvicc(name, settings.kvicc_stt_configured, "STT")
    if use_tts != use_stt:
        # L'audio du TTS KVICC n'est pas lisible par le STT mock, et inversement.
        raise ProviderNotConfiguredError(
            "Configuration KVICC incomplète : définissez KVICC_TTS_URL et KVICC_STT_URL "
            "ensemble, ou utilisez --provider mock."
        )
    if not use_tts:
        return MockTTSProvider(), MockSTTProvider()
    client = client_from_settings(settings, limiter=limiter)
    return (
        KviccTTSProvider.from_settings(settings, client),
        KviccSTTProvider.from_settings(settings, client),
    )
