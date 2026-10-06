import shutil
from pathlib import Path

import pytest

from xamxam.media import AudioError, audio_duration, split_audio, wav_to_ogg_opus
from xamxam.media import audio as audio_module
from xamxam.providers import MockTTSProvider

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg requis")


def _wav(seconds: int) -> bytes:
    return MockTTSProvider(seconds_per_char=1.0).synthesize("x" * seconds)


@requires_ffmpeg
def test_wav_to_ogg_opus(tmp_path: Path) -> None:
    ogg = wav_to_ogg_opus(_wav(3))
    assert ogg.startswith(b"OggS") and b"OpusHead" in ogg
    path = tmp_path / "note.ogg"
    path.write_bytes(ogg)
    assert audio_duration(path) == pytest.approx(3.0, abs=0.1)


@requires_ffmpeg
def test_split_audio_into_60_second_chunks(tmp_path: Path) -> None:
    path = tmp_path / "long.ogg"
    path.write_bytes(wav_to_ogg_opus(_wav(70)))
    chunks = split_audio(path, tmp_path / "morceaux", chunk_seconds=60)
    durations = [audio_duration(chunk) for chunk in chunks]
    assert len(chunks) == 2
    assert durations[0] == pytest.approx(60, abs=0.5) and durations[1] == pytest.approx(10, abs=0.5)


@requires_ffmpeg
def test_invalid_audio(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="échoué"):
        wav_to_ogg_opus(b"pas un wav")
    path = tmp_path / "faux.ogg"
    path.write_bytes(b"rien")
    with pytest.raises(AudioError):
        audio_duration(path)


def test_missing_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_module.shutil, "which", lambda name: None)
    with pytest.raises(AudioError, match="introuvable"):
        wav_to_ogg_opus(b"")
