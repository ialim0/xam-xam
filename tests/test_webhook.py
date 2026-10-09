import json

import pytest
from fastapi.testclient import TestClient

from fakes import FakeGraph, build_bot, image_message, webhook_payload
from xamxam.config import Settings
from xamxam.llm.mock import ScriptedLLM
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockTTSProvider
from xamxam.whatsapp import create_app
from xamxam.whatsapp.signature import SIGNATURE_HEADER, compute_signature, is_valid_signature

SECRET = "secret-app-test"
SETTINGS = Settings(whatsapp_app_secret=SECRET, whatsapp_verify_token="jeton-verif")


def test_signature() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    header = compute_signature(body, SECRET)
    assert header.startswith("sha256=")
    assert is_valid_signature(body, header, SECRET)
    assert not is_valid_signature(body + b" ", header, SECRET)
    assert not is_valid_signature(body, header, "autre-secret")
    assert not is_valid_signature(body, header.removeprefix("sha256="), SECRET)
    assert not is_valid_signature(body, None, SECRET)


@pytest.fixture
def client(pipeline: XamXamPipeline) -> TestClient:
    bot = build_bot(FakeGraph(), ScriptedLLM([]), pipeline=pipeline)
    return TestClient(create_app(SETTINGS, pipeline=pipeline, tts=MockTTSProvider(), bot=bot))


def test_webhook_verification(client: TestClient) -> None:
    params = {"hub.mode": "subscribe", "hub.verify_token": "jeton-verif", "hub.challenge": "42"}
    response = client.get("/webhook", params=params)
    assert (response.status_code, response.text) == (200, "42")
    bad = client.get("/webhook", params={**params, "hub.verify_token": "faux"})
    assert bad.status_code == 403


def _post(client: TestClient, payload: dict, *, secret: str = SECRET):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook",
        content=body,
        headers={
            SIGNATURE_HEADER: compute_signature(body, secret),
            "Content-Type": "application/json",
        },
    )


def test_webhook_rejects_bad_signature(client: TestClient) -> None:
    assert _post(client, webhook_payload(image_message()), secret="faux").status_code == 401


def test_webhook_rejects_unreadable_body(client: TestClient) -> None:
    body = b"pas du json"
    response = client.post(
        "/webhook", content=body, headers={SIGNATURE_HEADER: compute_signature(body, SECRET)}
    )
    assert response.status_code == 400


def test_webhook_ignores_status_notifications(client: TestClient) -> None:
    payload = webhook_payload()
    payload["entry"][0]["changes"][0]["value"] = {"statuses": [{"id": "wamid.x"}]}
    assert _post(client, payload).json() == {"status": "received"}


def test_webhook_without_configuration(pipeline: XamXamPipeline) -> None:
    client = TestClient(create_app(Settings(), pipeline=pipeline, tts=MockTTSProvider()))
    assert client.post("/webhook", json={}).status_code == 503
    assert client.get("/webhook", params={"hub.mode": "subscribe"}).status_code == 403
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["bot_ready"] is False
    assert "GEMINI_API_KEY" in health["missing_variables"]
    assert health["llm"] is None
    assert "LOG_HASH_KEY" not in health["missing_variables"]
    assert "KVICC_API_KEY" not in health["missing_variables"]
    assert client.get("/ready").status_code == 503


def test_health_reports_active_llm(client: TestClient) -> None:
    assert client.get("/health").json()["llm"] == {
        "provider": "mock",
        "model": "scripted",
        "agent": "scripted-agent",
    }
    assert client.get("/ready").json()["status"] == "ok"


BOT_SETTINGS = {
    "whatsapp_token": "t",
    "whatsapp_phone_number_id": "1",
    "whatsapp_verify_token": "v",
    "whatsapp_app_secret": "s",
    "gemini_api_key": "g",
}
KIRIKU = {
    "kvicc_tts_url": "https://kiriku.test/v1/audio/speech",
    "kvicc_stt_url": "https://kiriku.test/v1/audio/transcriptions",
    "kvicc_api_key": "test-key",
}


def test_bot_refuses_translation_mode_without_translator(pipeline: XamXamPipeline) -> None:
    from xamxam.llm import LLMConfigurationError

    settings = Settings(**BOT_SETTINGS, translate_from_french=True)
    with pytest.raises(LLMConfigurationError, match="aucun traducteur"):
        create_app(settings, pipeline=pipeline, tts=MockTTSProvider())


def test_bot_starts_with_gemini_only(pipeline: XamXamPipeline) -> None:
    client = TestClient(create_app(Settings(**BOT_SETTINGS), pipeline=pipeline))
    health = client.get("/health").json()
    assert health["llm"] == {
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "agent": "gemini-3.5-flash",
    }
    assert health["bot_ready"] and not health["voice"] and not health["video"]


def test_bot_enables_voice_and_video_when_configured(pipeline: XamXamPipeline) -> None:
    settings = Settings(**BOT_SETTINGS, **KIRIKU, timalens_api_key="tlak_test")
    health = TestClient(create_app(settings, pipeline=pipeline)).get("/health").json()
    assert health["voice"] and health["video"]
