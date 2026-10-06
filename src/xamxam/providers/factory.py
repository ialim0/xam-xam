"""Choix du fournisseur TTS / STT selon la configuration."""

from __future__ import annotations

import logging
from enum import StrEnum

from xamxam.config import Settings
from xamxam.providers.base import STTProvider, TTSProvider
from xamxam.providers.kvicc import KviccSTTProvider, KviccTTSProvider
from xamxam.providers.mock import MockSTTProvider, MockTTSProvider

logger = logging.getLogger(__name__)


class ProviderName(StrEnum):
    AUTO = "auto"  # KVICC si configuré, sinon mock
    MOCK = "mock"
    KVICC = "kvicc"


def create_tts_provider(name: ProviderName, settings: Settings) -> TTSProvider:
    if name is ProviderName.KVICC or (name is ProviderName.AUTO and settings.kvicc_tts_configured):
        return KviccTTSProvider.from_settings(settings)
    if name is ProviderName.AUTO:
        logger.info("TTS KVICC non configuré : utilisation du TTS mock.")
    return MockTTSProvider()


def create_stt_provider(name: ProviderName, settings: Settings) -> STTProvider:
    if name is ProviderName.KVICC or (name is ProviderName.AUTO and settings.kvicc_stt_configured):
        return KviccSTTProvider.from_settings(settings)
    if name is ProviderName.AUTO:
        logger.info("STT KVICC non configuré : utilisation du STT mock.")
    return MockSTTProvider()
