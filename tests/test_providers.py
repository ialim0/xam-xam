import io
import wave

import pytest

from xamxam.config import Settings
from xamxam.providers import (
    MockSTTProvider,
    MockTTSProvider,
    ProviderError,
    ProviderName,
    ProviderNotConfiguredError,
    create_stt_provider,
    create_tts_provider,
)
from xamxam.providers.kvicc import KviccSTTProvider, KviccTTSProvider

_KVICC = Settings(
    kvicc_tts_url="https://tts.example",
    kvicc_stt_url="https://stt.example",
    kvicc_api_key="secret-key",
)


def test_mock_round_trip_preserves_text() -> None:
    text = "Hypoténuse bi, ñaar fukk ak juróom."
    audio = MockTTSProvider().synthesize(text)
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16_000)
        assert wav.getnframes() > 0
    assert MockSTTProvider().transcribe(audio) == text


def test_mock_stt_applies_transform() -> None:
    audio = MockTTSProvider().synthesize("triangle")
    assert MockSTTProvider(str.upper).transcribe(audio) == "TRIANGLE"


def test_mock_stt_rejects_foreign_audio() -> None:
    with pytest.raises(ProviderError):
        MockSTTProvider().transcribe(b"RIFF\x00\x00\x00\x00WAVE")


def test_auto_uses_mock_without_keys() -> None:
    assert isinstance(create_tts_provider(ProviderName.AUTO, Settings()), MockTTSProvider)
    assert isinstance(create_stt_provider(ProviderName.AUTO, Settings()), MockSTTProvider)


def test_auto_uses_kvicc_when_configured() -> None:
    assert isinstance(create_tts_provider(ProviderName.AUTO, _KVICC), KviccTTSProvider)
    assert isinstance(create_stt_provider(ProviderName.AUTO, _KVICC), KviccSTTProvider)


def test_kvicc_requires_configuration() -> None:
    with pytest.raises(ProviderNotConfiguredError, match="KVICC_TTS_URL"):
        create_tts_provider(ProviderName.KVICC, Settings())
    with pytest.raises(ProviderNotConfiguredError, match="KVICC_STT_URL"):
        create_stt_provider(ProviderName.KVICC, Settings())


def test_kvicc_from_settings_hides_key() -> None:
    tts = KviccTTSProvider.from_settings(_KVICC)
    assert "secret-key" not in repr(tts)
