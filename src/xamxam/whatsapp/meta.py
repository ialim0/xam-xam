"""Client de l'API Graph de Meta (WhatsApp Cloud) : médias et envoi de messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from xamxam.errors import XamXamError
from xamxam.metrics import record_request

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.facebook.com"
# Taille maximale acceptée pour un média reçu (les images WhatsApp font quelques Mo).
MAX_MEDIA_BYTES = 16 * 1024 * 1024
MAX_TEXT_CHARS = 4096


class MetaError(XamXamError):
    """Échec d'un appel à l'API Graph."""


@dataclass(frozen=True)
class DownloadedMedia:
    content: bytes
    mime_type: str


class MetaClient:
    """Appels asynchrones à l'API Graph, authentifiés par le jeton d'accès WhatsApp."""

    def __init__(
        self,
        *,
        token: str,
        phone_number_id: str,
        api_version: str,
        base_url: str = GRAPH_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._api = f"{base_url.rstrip('/')}/{api_version}"
        self._http = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    def __repr__(self) -> str:
        return f"MetaClient(api={self._api!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        record_request("meta")
        try:
            response = await self._http.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise MetaError(f"API Graph injoignable ({type(exc).__name__}).") from exc
        if response.is_error:
            # Le corps d'erreur de Meta ne contient pas de contenu utilisateur, mais on le tronque.
            raise MetaError(f"API Graph : erreur {response.status_code} : {response.text[:300]}")
        return response

    async def download_media(self, media_id: str) -> DownloadedMedia:
        """Deux étapes : récupérer l'URL temporaire du média, puis son contenu."""
        info = (await self._request("GET", f"{self._api}/{media_id}")).json()
        url, mime_type = info.get("url"), info.get("mime_type", "application/octet-stream")
        if not url:
            raise MetaError("API Graph : URL du média absente.")
        if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
            raise MetaError("Média trop volumineux.")
        response = await self._request("GET", url)
        if len(response.content) > MAX_MEDIA_BYTES:
            raise MetaError("Média trop volumineux.")
        return DownloadedMedia(response.content, mime_type)

    async def upload_media(self, content: bytes, mime_type: str, filename: str) -> str:
        """Téléverse un média et retourne son identifiant."""
        response = await self._request(
            "POST",
            f"{self._api}/{self._phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, content, mime_type)},
        )
        media_id = response.json().get("id")
        if not media_id:
            raise MetaError("API Graph : identifiant du média absent.")
        return str(media_id)

    async def _send(self, to: str, message: dict[str, object]) -> None:
        await self._request(
            "POST",
            f"{self._api}/{self._phone_number_id}/messages",
            json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
            | message,
        )

    async def send_text(self, to: str, body: str) -> None:
        await self._send(to, {"type": "text", "text": {"body": body[:MAX_TEXT_CHARS]}})

    async def send_buttons(self, to: str, body: str, titles: list[str]) -> None:
        """Message avec 1 à 3 boutons de réponse rapide (libellés de 20 caractères au plus)."""
        buttons = [
            {"type": "reply", "reply": {"id": f"b{index}", "title": title[:20]}}
            for index, title in enumerate(titles[:3], start=1)
        ]
        await self._send(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body[:1024]},
                    "action": {"buttons": buttons},
                },
            },
        )

    async def mark_read_and_typing(self, message_id: str) -> None:
        """Coche bleue et « en train d'écrire » (25 s au plus, ou jusqu'à la réponse)."""
        await self._request(
            "POST",
            f"{self._api}/{self._phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {"type": "text"},
            },
        )

    async def send_audio(self, to: str, media_id: str) -> None:
        # Un audio OGG Opus est présenté par WhatsApp comme une note vocale.
        await self._send(to, {"type": "audio", "audio": {"id": media_id}})

    async def send_video(self, to: str, link: str, caption: str = "") -> None:
        """Vidéo par lien HTTPS : Meta la télécharge lui-même (16 Mo au plus)."""
        video: dict[str, str] = {"link": link}
        if caption:
            video["caption"] = caption
        await self._send(to, {"type": "video", "video": video})
