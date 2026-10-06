"""Doublures partagées par les tests du bot : API Graph, LLM, STT, TTS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from xamxam.llm import MathSolution
from xamxam.providers import MockTTSProvider, RateLimiter, STTProvider
from xamxam.whatsapp.bot import XamXamBot
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.meta import MetaClient
from xamxam.whatsapp.privacy import IdHasher
from xamxam.whatsapp.settings import BotSettings

GRAPH_VERSION = "v23.0"
PHONE_ID = "1234567890"
STUDENT = "221771234567"


@dataclass
class FakeGraph:
    """API Graph simulée : sert les médias et enregistre les envois, dans l'ordre."""

    media: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    sent: list[dict[str, Any]] = field(default_factory=list)
    uploads: list[bytes] = field(default_factory=list)
    fail_downloads: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "media.test":
            content, mime = self.media[path.strip("/")]
            return httpx.Response(200, content=content, headers={"Content-Type": mime})
        if request.method == "GET":
            media_id = path.rsplit("/", 1)[-1]
            if self.fail_downloads or media_id not in self.media:
                return httpx.Response(404, json={"error": {"message": "Unknown media"}})
            content, mime = self.media[media_id]
            return httpx.Response(
                200,
                json={
                    "url": f"https://media.test/{media_id}",
                    "mime_type": mime,
                    "file_size": len(content),
                },
            )
        if path.endswith("/media"):
            self.uploads.append(request.read())
            return httpx.Response(200, json={"id": f"upload-{len(self.uploads)}"})
        if path.endswith("/messages"):
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})
        return httpx.Response(404)

    def client(self) -> MetaClient:
        return MetaClient(
            token="test-token",
            phone_number_id=PHONE_ID,
            api_version=GRAPH_VERSION,
            transport=httpx.MockTransport(self.handler),
        )

    @property
    def texts(self) -> list[str]:
        return [m["text"]["body"] for m in self.sent if m["type"] == "text"]

    @property
    def kinds(self) -> list[str]:
        return [m["type"] for m in self.sent]


class FakeSTT(STTProvider):
    """STT qui renvoie un texte fixe et garde les audios reçus."""

    name = "faux-stt"

    def __init__(self, text: str = "Naka laa wara def ?") -> None:
        self.text = text
        self.received: list[bytes] = []

    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        self.received.append(audio)
        return self.text


class RecordingTTS(MockTTSProvider):
    """TTS mock qui garde les textes reçus."""

    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []

    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        self.texts.append(text)
        return super().synthesize(text, language=language)


def make_solution(**overrides: Any) -> MathSolution:
    """Solution valide d'un exercice de Pythagore (AB = 4, AC = 6, BC = √52)."""
    data: dict[str, Any] = {
        "statut": "ok",
        "enonce": "ABC est rectangle en A, AB = 4 cm et AC = 6 cm. Calcule BC.",
        "notion": "pythagore",
        "etapes": ["BC² = AB² + AC²", "BC² = 16 + 36 = 52", "BC = √52 ≈ 7,21 cm"],
        "reponse_finale": "BC = √52 ≈ 7,21 cm",
        "termes_cles": ["hypoténuse", "théorème de Pythagore"],
        "explication_wo": (
            "Données yi : AB = 4 cm, AC = 6 cm. BC mooy hypoténuse bi. "
            "Ci théorème de Pythagore, BC² = AB² + AC²."
        ),
        "calcul": {
            "type": "pythagore_hypotenuse",
            "donnees": [{"nom": "cote1", "valeur": 4}, {"nom": "cote2", "valeur": 6}],
            "resultat": "√52 ≈ 7,21",
        },
    }
    for key, value in overrides.items():
        if key == "resultat":
            data["calcul"] = {**data["calcul"], "resultat": value}
        else:
            data[key] = value
    return MathSolution.model_validate(data)


def build_bot(
    graph: FakeGraph,
    llm: Any,
    *,
    pipeline: Any,
    stt: STTProvider | None = None,
    tts: Any = None,
    settings: BotSettings | None = None,
    limiter: RateLimiter | None = None,
    unlimited: frozenset[str] = frozenset(),
) -> XamXamBot:
    return XamXamBot(
        meta=graph.client(),
        llm=llm,
        stt=stt or FakeSTT(),
        tts=tts or RecordingTTS(),
        pipeline=pipeline,
        kiriku_limiter=limiter or RateLimiter(30),
        hasher=IdHasher("cle-de-test"),
        settings=settings or BotSettings(grouping_window_seconds=0),
        messages=BotMessages(),
        unlimited_numbers=unlimited,
    )


def webhook_payload(*messages: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": PHONE_ID},
                            "contacts": [{"wa_id": STUDENT, "profile": {"name": "Awa"}}],
                            "messages": list(messages),
                        },
                    }
                ],
            }
        ],
    }


def image_message(message_id: str = "wamid.img", media_id: str = "img-1") -> dict[str, Any]:
    return {
        "from": STUDENT,
        "id": message_id,
        "timestamp": "1760000000",
        "type": "image",
        "image": {"id": media_id, "mime_type": "image/jpeg"},
    }


def audio_message(message_id: str = "wamid.aud", media_id: str = "aud-1") -> dict[str, Any]:
    return {
        "from": STUDENT,
        "id": message_id,
        "timestamp": "1760000001",
        "type": "audio",
        "audio": {"id": media_id, "mime_type": "audio/ogg; codecs=opus", "voice": True},
    }


def text_message(body: str, message_id: str = "wamid.txt") -> dict[str, Any]:
    return {
        "from": STUDENT,
        "id": message_id,
        "timestamp": "1760000002",
        "type": "text",
        "text": {"body": body},
    }
