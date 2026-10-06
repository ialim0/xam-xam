"""Fournisseurs de synthèse (TTS) et de reconnaissance (STT) vocales."""

from xamxam.providers.base import (
    ProviderError,
    ProviderNotConfiguredError,
    STTProvider,
    TTSProvider,
)
from xamxam.providers.cache import CachedSTTProvider, CachedTTSProvider
from xamxam.providers.factory import (
    ProviderName,
    create_providers,
    create_stt_provider,
    create_tts_provider,
)
from xamxam.providers.mock import MockSTTProvider, MockTTSProvider
from xamxam.providers.ratelimit import RateLimiter

__all__ = [
    "CachedSTTProvider",
    "CachedTTSProvider",
    "MockSTTProvider",
    "MockTTSProvider",
    "ProviderError",
    "ProviderName",
    "ProviderNotConfiguredError",
    "RateLimiter",
    "STTProvider",
    "TTSProvider",
    "create_providers",
    "create_stt_provider",
    "create_tts_provider",
]
