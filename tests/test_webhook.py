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
    assert health["bot_ready"] is False
    assert "LLM_PROVIDER" in health["missing_variables"]
    assert health["llm"] is None
    assert "LOG_HASH_KEY" not in health["missing_variables"]


def test_health_reports_active_llm(client: TestClient) -> None:
    assert client.get("/health").json()["llm"] == {"provider": "mock", "model": "scripted"}


BOT_SETTINGS = {
    "whatsapp_token": "t",
    "whatsapp_phone_number_id": "1",
    "whatsapp_verify_token": "v",
    "whatsapp_app_secret": "s",
}


def test_bot_refuses_to_start_with_unlisted_model(pipeline: XamXamPipeline) -> None:
    from xamxam.llm import LLMConfigurationError

    settings = Settings(
        **BOT_SETTINGS,
        llm_provider="selfhosted",
        selfhosted_base_url="http://vllm:8000/v1",
        selfhosted_model="modele/non-autorise",
    )
    with pytest.raises(LLMConfigurationError, match="absent de la liste blanche"):
        create_app(settings, pipeline=pipeline, tts=MockTTSProvider())


def test_bot_refuses_translation_mode_without_translator(pipeline: XamXamPipeline) -> None:
    from xamxam.llm import LLMConfigurationError

    settings = Settings(
        **BOT_SETTINGS,
        llm_provider="selfhosted",
        selfhosted_base_url="http://vllm:8000/v1",
        selfhosted_model="Qwen/Qwen3-VL-8B-Instruct",
        translate_from_french=True,
    )
    with pytest.raises(LLMConfigurationError, match="aucun traducteur"):
        create_app(settings, pipeline=pipeline, tts=MockTTSProvider())


def test_bot_starts_with_allowed_selfhosted_model(pipeline: XamXamPipeline) -> None:
    settings = Settings(
        **BOT_SETTINGS,
        llm_provider="selfhosted",
        selfhosted_base_url="http://vllm:8000/v1",
        selfhosted_model="Qwen/Qwen3-VL-8B-Instruct",
    )
    health = TestClient(create_app(settings, pipeline=pipeline, tts=MockTTSProvider()))
    assert health.get("/health").json()["llm"] == {
        "provider": "selfhosted",
        "model": "Qwen/Qwen3-VL-8B-Instruct",
    }
