import io
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from fakes import FakeTimaLens
from xamxam.config import Settings
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockSTTProvider, MockTTSProvider
from xamxam.timalens import (
    VIDEO_DISABLED_MESSAGE,
    RenderRefusedError,
    TimaLensClient,
    TimaLensDisabledError,
    TimaLensError,
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


@pytest.mark.anyio
async def test_timalens_errors_keep_only_status_and_code() -> None:
    api = FakeTimaLens(affordable=False)
    client = api.client()
    with pytest.raises(ValueError, match="vide"):
        await client.create_project("  ", title="t")
    with pytest.raises(RenderRefusedError, match="insuffisants") as refused:
        await client.make_video("Hypoténuse bi", title="t")
    assert refused.value.code == "insufficient_credits"
    assert "POST /projects/p1/confirm" not in api.paths

    unauthorized = TimaLensClient("tlak_autre", transport=httpx.MockTransport(api.handler))
    with pytest.raises(TimaLensError) as raised:
        await unauthorized.job_status("p1")
    assert (raised.value.status, raised.value.code) == (401, "unauthenticated")


@pytest.mark.anyio
async def test_timalens_wait_gives_up_after_deadline() -> None:
    now = [0.0]
    api = FakeTimaLens(states=["generating"])

    async def advance(seconds: float) -> None:
        now[0] += seconds

    client = TimaLensClient(
        "tlak_test",
        transport=httpx.MockTransport(api.handler),
        poll_interval=10,
        max_wait_seconds=30,
        sleep=advance,
        clock=lambda: now[0],
    )
    with pytest.raises(TimaLensError, match="non atteint après 30 s"):
        await client.wait_for("p1", "preview_ready")
    assert api.paths.count("GET /jobs/p1") == 4


@pytest.mark.anyio
async def test_timalens_narration_uses_detected_language() -> None:
    api = FakeTimaLens(detected_language="fr")
    client = api.client()
    narration = await client.upload_narration(b"OggS...", mime_type="audio/ogg", filename="n.ogg")
    assert (narration.asset_id, narration.language) == ("a1", "fr")
    await client.create_project("Explication", title="Titre", narration=narration)
    project = api.requests[-1][2]
    assert project["language"] == "fr"
    assert project["source_text"] == "Titre\n\nExplication"


@pytest.fixture
def client(pipeline: XamXamPipeline) -> TestClient:
    return TestClient(
        create_app(Settings(enable_dev_routes=True), pipeline=pipeline, tts=MockTTSProvider())
    )


def test_dev_speak_is_disabled_by_default(pipeline: XamXamPipeline) -> None:
    app = create_app(Settings(), pipeline=pipeline, tts=MockTTSProvider())
    assert TestClient(app).post("/dev/speak", json={"text": "AB²"}).status_code == 404


def test_dev_speak_returns_prepared_audio(client: TestClient) -> None:
    response = client.post("/dev/speak", json={"text": "L'hypoténuse : AB² = 9 cm²"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content), "rb") as wav:
        assert wav.getnframes() > 0
    assert MockSTTProvider().transcribe(response.content) == (
        "L'ipoteniws: aa bee au carré égale neuf centimètres carrés"
    )
