import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from xamxam.providers import CachedTTSProvider, MockSTTProvider, MockTTSProvider, TTSProvider
from xamxam.providers.cache import DiskCache


class CountingTTS(TTSProvider):
    """TTS factice qui compte les synthèses réellement effectuées."""

    name = "compteur"

    def __init__(self, speed: float = 1.0) -> None:
        self.calls = 0
        self.speed = speed
        self._inner = MockTTSProvider()

    @property
    def cache_identity(self) -> str:
        return f"compteur:{self.speed}"

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        self.calls += 1
        return self._inner.synthesize(text, language=language)


def test_same_text_is_synthesized_once(tmp_path: Path) -> None:
    inner = CountingTTS()
    tts = CachedTTSProvider(inner, tmp_path)
    first = tts.synthesize("Hypoténuse bi")
    second = tts.synthesize("Hypoténuse bi")
    assert first == second
    assert inner.calls == 1
    assert (tts.hits, tts.misses) == (1, 1)
    assert MockSTTProvider().transcribe(second) == "Hypoténuse bi"


def test_cache_survives_a_new_instance(tmp_path: Path) -> None:
    CachedTTSProvider(CountingTTS(), tmp_path).synthesize("ñaar fukk")
    inner = CountingTTS()
    CachedTTSProvider(inner, tmp_path).synthesize("ñaar fukk")
    assert inner.calls == 0


def test_key_depends_on_text_language_and_provider_settings(tmp_path: Path) -> None:
    tts = CachedTTSProvider(CountingTTS(), tmp_path)
    keys = {
        tts.cache_key("triangle", "wo"),
        tts.cache_key("Triangle", "wo"),
        tts.cache_key("triangle", "ff"),
        CachedTTSProvider(CountingTTS(speed=1.2), tmp_path).cache_key("triangle", "wo"),
    }
    assert len(keys) == 4


def test_no_temporary_file_is_left(tmp_path: Path) -> None:
    tts = CachedTTSProvider(CountingTTS(), tmp_path)
    tts.synthesize("triangle")
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert [p.suffix for p in files] == [".wav"]
    assert files[0] == tts.cache_path("triangle", "wo")


def test_concurrent_cache_writes_use_separate_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = DiskCache(tmp_path, ".wav", name="tts")
    barrier = threading.Barrier(2)
    original = Path.write_bytes

    def write_together(path: Path, value: bytes) -> int:
        count = original(path, value)
        if path.suffix == ".tmp":
            barrier.wait(timeout=5)
        return count

    monkeypatch.setattr(Path, "write_bytes", write_together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: cache.put("same-key", value), (b"one", b"two")))
    assert results == [None, None]
    assert cache.get("same-key") in (b"one", b"two")
    assert list(tmp_path.rglob("*.tmp")) == []


class CountingSTT(MockSTTProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        self.calls += 1
        return super().transcribe(audio, language=language)


def test_stt_cache_by_audio_fingerprint(tmp_path: Path) -> None:
    from xamxam.providers import CachedSTTProvider

    audio = MockTTSProvider().synthesize("ñaar fukk")
    inner = CountingSTT()
    stt = CachedSTTProvider(inner, tmp_path)
    assert stt.transcribe(audio) == stt.transcribe(audio) == "ñaar fukk"
    assert inner.calls == 1 and (stt.hits, stt.misses) == (1, 1)
    # Autre langue ou autre audio : nouvelle transcription.
    stt.transcribe(audio, language="ff")
    stt.transcribe(MockTTSProvider().synthesize("ñett"))
    assert inner.calls == 3
    # Le cache survit à une nouvelle instance.
    fresh = CountingSTT()
    assert CachedSTTProvider(fresh, tmp_path).transcribe(audio) == "ñaar fukk"
    assert fresh.calls == 0
