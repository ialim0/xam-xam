import io
import json
import wave

import httpx
import pytest

from xamxam.config import Settings
from xamxam.providers import (
    ProviderError,
    ProviderName,
    ProviderNotConfiguredError,
    create_providers,
)
from xamxam.providers.audio import concat_wav
from xamxam.providers.chunking import split_text
from xamxam.providers.kvicc import (
    MAX_TTS_CHARS,
    KviccClient,
    KviccSTTProvider,
    KviccTTSProvider,
)

TTS_URL = "https://kiriku.test/v1/audio/speech"
STT_URL = "https://kiriku.test/v1/audio/transcriptions"


def _wav(frames: int, rate: int = 22_050) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x01\x00" * frames)
    return buffer.getvalue()


def _frames(audio: bytes) -> int:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        return wav.getnframes()


class FakeTime:
    """Horloge et sommeil simulés : aucun test n'attend réellement."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(handler, fake_time: FakeTime | None = None, **kwargs) -> KviccClient:
    fake_time = fake_time or FakeTime()
    return KviccClient(
        "sk-kiriku-test",
        transport=httpx.MockTransport(handler),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **kwargs,
    )


# --- Découpage et assemblage ---------------------------------------------------


def test_split_text_keeps_short_text() -> None:
    assert split_text("  Salaam aleekum.  ", 512) == ["Salaam aleekum."]
    assert split_text("   ", 512) == []


def test_split_text_prefers_sentence_boundaries() -> None:
    text = "Première phrase. Deuxième phrase, assez longue. Troisième."
    assert split_text(text, 30) == [
        "Première phrase.",
        "Deuxième phrase, assez longue.",
        "Troisième.",
    ]


def test_split_text_never_exceeds_limit() -> None:
    text = ("mot " * 400 + "x" * 50).strip()
    chunks = split_text(text, 40)
    assert all(len(chunk) <= 40 for chunk in chunks)
    assert " ".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_concat_wav() -> None:
    assert _frames(concat_wav([_wav(100), _wav(50)])) == 150
    with pytest.raises(ProviderError, match="formats différents"):
        concat_wav([_wav(10, 22_050), _wav(10, 16_000)])
    with pytest.raises(ProviderError, match="illisible"):
        concat_wav([_wav(10), b"pas un wav"])


# --- TTS ---------------------------------------------------------------------


def test_tts_request_follows_the_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=_wav(10), headers={"Content-Type": "audio/wav"})

    tts = KviccTTSProvider(TTS_URL, _client(handler), speed=1.0)
    assert _frames(tts.synthesize("Salaam aleekum")) == 10

    [request] = requests
    assert str(request.url) == TTS_URL
    assert request.headers["Authorization"] == "Bearer sk-kiriku-test"
    assert request.headers["User-Agent"].startswith("xamxam/")
    assert json.loads(request.content) == {
        "model": "kiriku-tts",
        "input": "Salaam aleekum",
        "voice": "wolof",
        "response_format": "wav",
        "speed": 1.0,
    }


def test_tts_splits_long_texts_and_reassembles_audio() -> None:
    inputs: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs.append(json.loads(request.content)["input"])
        return httpx.Response(200, content=_wav(100))

    sentence = "Ci benn triangle rectangle, hypoténuse bi mooy wet bi gën a gudd. "
    audio = KviccTTSProvider(TTS_URL, _client(handler)).synthesize(sentence * 20)
    assert len(inputs) > 1
    assert all(len(text) <= MAX_TTS_CHARS for text in inputs)
    assert _frames(audio) == 100 * len(inputs)


def test_tts_rejects_unsupported_language() -> None:
    tts = KviccTTSProvider(TTS_URL, _client(lambda r: httpx.Response(200)))
    with pytest.raises(ProviderError, match="srr"):
        tts.synthesize("texte", language="srr")


# --- STT ---------------------------------------------------------------------


def test_stt_request_follows_the_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": " salaam aleekum "})

    stt = KviccSTTProvider(STT_URL, _client(handler))
    assert stt.transcribe(_wav(10), language="srr") == "salaam aleekum"

    [request] = requests
    body = request.read()
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    for expected in (b'name="model"', b"m-kiriku-asr", b'name="language"', b"serer", b"RIFF"):
        assert expected in body


def test_stt_rejects_unexpected_response() -> None:
    stt = KviccSTTProvider(STT_URL, _client(lambda r: httpx.Response(200, text="oups")))
    with pytest.raises(ProviderError, match="inattendue"):
        stt.transcribe(_wav(10))


# --- Erreurs, nouvelles tentatives et débit -------------------------------------


def test_retries_after_rate_limit() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(503),
            httpx.Response(200, json={"text": "ok"}),
        ]
    )
    fake_time = FakeTime()
    stt = KviccSTTProvider(STT_URL, _client(lambda r: next(responses), fake_time, min_interval=0))
    assert stt.transcribe(_wav(10)) == "ok"
    assert fake_time.sleeps == [7.0, 2.0]


def test_gives_up_after_max_retries() -> None:
    error = {"error": {"message": "Rate limit reached", "type": "rate_limit_error"}}
    client = _client(lambda r: httpx.Response(429, json=error), max_retries=1, min_interval=0)
    with pytest.raises(ProviderError, match="429 : Rate limit reached"):
        KviccSTTProvider(STT_URL, client).transcribe(_wav(10))


def test_invalid_key_gives_a_clear_error() -> None:
    error = {"error": {"message": "Invalid API key", "type": "authentication_error"}}
    client = _client(lambda r: httpx.Response(401, json=error))
    with pytest.raises(ProviderError, match="Vérifiez KVICC_API_KEY"):
        KviccTTSProvider(TTS_URL, client).synthesize("salaam")


def test_network_errors_are_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connexion refusée")

    with pytest.raises(ProviderError, match="injoignable"):
        KviccTTSProvider(TTS_URL, _client(handler)).synthesize("salaam")


def test_requests_are_spaced_to_respect_the_rate_limit() -> None:
    fake_time = FakeTime()
    client = _client(lambda r: httpx.Response(200, json={"text": "ok"}), fake_time)
    stt = KviccSTTProvider(STT_URL, client)
    for _ in range(3):
        stt.transcribe(_wav(10))
    # 30 requêtes par minute : 2 s entre deux requêtes.
    assert fake_time.sleeps == [2.0, 2.0]


# --- Configuration -------------------------------------------------------------


def test_create_providers_shares_one_client() -> None:
    settings = Settings(kvicc_tts_url=TTS_URL, kvicc_stt_url=STT_URL, kvicc_api_key="sk-kiriku-x")
    tts, stt = create_providers(ProviderName.AUTO, settings)
    assert isinstance(tts, KviccTTSProvider) and isinstance(stt, KviccSTTProvider)
    assert tts._client is stt._client
    assert "sk-kiriku-x" not in repr(tts) + repr(stt) + repr(tts._client)


def test_create_providers_rejects_partial_configuration() -> None:
    settings = Settings(kvicc_tts_url=TTS_URL, kvicc_api_key="sk-kiriku-x")
    with pytest.raises(ProviderNotConfiguredError, match="incomplète"):
        create_providers(ProviderName.AUTO, settings)
