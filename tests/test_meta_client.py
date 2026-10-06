import json

import httpx
import pytest

from fakes import GRAPH_VERSION, PHONE_ID
from xamxam.whatsapp.meta import MAX_MEDIA_BYTES, MetaClient, MetaError

pytestmark = pytest.mark.anyio


def _client(handler) -> MetaClient:
    return MetaClient(
        token="jeton",
        phone_number_id=PHONE_ID,
        api_version=GRAPH_VERSION,
        transport=httpx.MockTransport(handler),
    )


async def test_download_media_in_two_steps() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == f"/{GRAPH_VERSION}/media-1":
            return httpx.Response(200, json={"url": "https://cdn.test/f", "mime_type": "image/png"})
        return httpx.Response(200, content=b"PNG")

    media = await _client(handler).download_media("media-1")
    assert (media.content, media.mime_type) == (b"PNG", "image/png")
    assert [str(r.url) for r in requests] == [
        f"https://graph.facebook.com/{GRAPH_VERSION}/media-1",
        "https://cdn.test/f",
    ]
    # Le téléchargement lui-même exige aussi le jeton.
    assert all(r.headers["Authorization"] == "Bearer jeton" for r in requests)


async def test_download_rejects_oversized_media() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"url": "https://cdn.test/f", "file_size": MAX_MEDIA_BYTES + 1}
        )

    with pytest.raises(MetaError, match="volumineux"):
        await _client(handler).download_media("media-1")


async def test_upload_and_send_messages() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "up-1"})
        return httpx.Response(200, json={"messages": [{"id": "wamid"}]})

    client = _client(handler)
    assert await client.upload_media(b"OggS...", "audio/ogg", "x.ogg") == "up-1"
    await client.send_audio("221770000000", "up-1")
    await client.send_text("221770000000", "Tontu bi : 5 cm")

    upload, audio, text = requests
    assert str(upload.url).endswith(f"/{PHONE_ID}/media")
    assert b'name="messaging_product"' in upload.content and b"OggS" in upload.content
    assert json.loads(audio.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "221770000000",
        "type": "audio",
        "audio": {"id": "up-1"},
    }
    assert json.loads(text.content)["text"] == {"body": "Tontu bi : 5 cm"}


async def test_errors_are_wrapped() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid OAuth access token"}})

    with pytest.raises(MetaError, match="401"):
        await _client(failing).send_text("221", "salut")

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé")

    with pytest.raises(MetaError, match="injoignable"):
        await _client(unreachable).send_text("221", "salut")
