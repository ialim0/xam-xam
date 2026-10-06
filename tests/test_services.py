import io
import wave

import pytest
from fastapi.testclient import TestClient

from xamxam.config import Settings
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockSTTProvider, MockTTSProvider
from xamxam.timalens import (
    VIDEO_DISABLED_MESSAGE,
    TimaLensClient,
    TimaLensDisabledError,
    build_timalens_client,
)
from xamxam.whatsapp import create_app


def test_settings_from_env_ignores_blank_values() -> None:
    settings = Settings.from_env({"KVICC_API_KEY": "  ", "TIMALENS_API_KEY": "tl-secret"})
    assert settings.kvicc_api_key is None
    assert settings.timalens_api_key == "tl-secret"
    assert "tl-secret" not in repr(settings)


def test_video_is_disabled_without_key(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        assert build_timalens_client(Settings()) is None
    assert VIDEO_DISABLED_MESSAGE in caplog.text


def test_timalens_client_requires_key_and_hides_it() -> None:
    with pytest.raises(TimaLensDisabledError):
        TimaLensClient("")
    client = build_timalens_client(Settings(timalens_api_key="tl-secret"))
    assert client is not None and "tl-secret" not in repr(client)
    with pytest.raises(ValueError, match="vide"):
        client.create_clip("  ")
    with pytest.raises(NotImplementedError):
        client.create_clip("Hypoténuse bi")


@pytest.fixture
def client(pipeline: XamXamPipeline) -> TestClient:
    return TestClient(create_app(Settings(), pipeline=pipeline, tts=MockTTSProvider()))


def test_health_reports_disabled_features(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "tts": "mock",
        "whatsapp_enabled": False,
        "video_enabled": False,
    }


def test_webhook_requires_whatsapp_token(client: TestClient) -> None:
    assert client.post("/webhook", json={}).status_code == 503


def test_webhook_accepts_messages_when_configured(pipeline: XamXamPipeline) -> None:
    app = create_app(Settings(whatsapp_token="t"), pipeline=pipeline, tts=MockTTSProvider())
    response = TestClient(app).post("/webhook", json={"entry": []})
    assert response.json() == {"status": "received"}


def test_dev_speak_returns_prepared_audio(client: TestClient) -> None:
    response = client.post("/dev/speak", json={"text": "L'hypoténuse : AB² = 9 cm²"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content), "rb") as wav:
        assert wav.getnframes() > 0
    assert MockSTTProvider().transcribe(response.content) == (
        "L'ipoteniws: A B au carré égale neuf centimètres carrés"
    )
