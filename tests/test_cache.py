from pathlib import Path

from xamxam.providers import CachedTTSProvider, MockSTTProvider, MockTTSProvider, TTSProvider


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
