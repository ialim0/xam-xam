"""Doublures partagées par les tests du bot : API Graph, LLM, STT, TTS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from xamxam.agent import ScriptedAgentModel
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
    read_receipts: list[str] = field(default_factory=list)
    fail_downloads: bool = False
    # Identifiants de média refusés à l'envoi (média expiré chez Meta, par exemple).
    rejected_media: set[str] = field(default_factory=set)

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
            body = json.loads(request.content)
            if body.get("status") == "read":  # coche bleue + « en train d'écrire »
                self.read_receipts.append(body["message_id"])
                return httpx.Response(200, json={"success": True})
            media = body.get(body.get("type", ""), {})
            if isinstance(media, dict) and media.get("id") in self.rejected_media:
                return httpx.Response(400, json={"error": {"message": "Media not found"}})
            self.sent.append(body)
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
    def buttons(self) -> list[list[str]]:
        return [
            [b["reply"]["title"] for b in m["interactive"]["action"]["buttons"]]
            for m in self.sent
            if m["type"] == "interactive"
        ]

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
    agent: Any = None,
    stt: STTProvider | None = None,
    tts: Any = None,
    voice: bool = True,
    video: Any = None,
    waiting_sticker: bytes | None = None,
    settings: BotSettings | None = None,
    limiter: RateLimiter | None = None,
    unlimited: frozenset[str] = frozenset(),
    state_path: Path | None = None,
) -> XamXamBot:
    return XamXamBot(
        meta=graph.client(),
        llm=llm,
        agent=agent if agent is not None else ScriptedAgentModel([]),
        # voice=False : bot sans Kiriku, qui répond en texte.
        stt=(stt or FakeSTT()) if voice else None,
        tts=(tts or RecordingTTS()) if voice else None,
        pipeline=pipeline,
        kiriku_limiter=limiter or RateLimiter(30),
        hasher=IdHasher("cle-de-test"),
        # Mode texte par défaut dans les tests ; le mode audio a ses propres tests.
        settings=settings or BotSettings(grouping_window_seconds=0, reply_mode="texte"),
        messages=BotMessages(),
        unlimited_numbers=unlimited,
        state_path=state_path,
        video=video,
        waiting_sticker=waiting_sticker,
    )


@dataclass
class FakeTimaLens:
    """API TimaLens simulée : chaque GET /jobs avance d'un état dans `states`."""

    states: list[str] = field(
        default_factory=lambda: ["generating", "preview_ready", "rendering", "exported"]
    )
    credits: float = 12.0
    affordable: bool = True
    detected_language: str | None = None  # langue renvoyée par l'envoi de l'audio
    uploads: list[bytes] = field(default_factory=list)
    requests: list[tuple[str, str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        multipart = request.headers.get("Content-Type", "").startswith("multipart/")
        body = json.loads(request.content) if request.content and not multipart else None
        self.requests.append((request.method, path, body))
        if request.headers.get("Authorization") != "Bearer tlak_test":
            return httpx.Response(401, json={"error": {"code": "unauthenticated"}})
        if (request.method, path) == ("POST", "/assets/custom-audio"):
            self.uploads.append(request.read())
            return httpx.Response(
                200,
                json={
                    "asset_id": "a1",
                    "duration_seconds": 42.0,
                    "transcript": "…",
                    "language": self.detected_language,
                },
            )
        if (request.method, path) == ("POST", "/projects"):
            return httpx.Response(201, json={"id": "p1", "state": "draft"})
        if (request.method, path) == ("POST", "/projects/p1/generate"):
            return httpx.Response(202, json={"state": "generating", "credits_charged": 0})
        if path == "/jobs/p1":
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            exported = state == "exported"
            return httpx.Response(
                200,
                json={
                    "id": "p1",
                    "state": state,
                    "progress": 100 if exported else 50,
                    "download_url": "https://cdn.timalens.test/p1.mp4" if exported else None,
                },
            )
        if path == "/projects/p1/quote":
            return httpx.Response(
                200,
                json={
                    "quote_token": "QT",
                    "estimated_credits": self.credits,
                    "affordable": self.affordable,
                },
            )
        if (request.method, path) == ("POST", "/projects/p1/confirm"):
            return httpx.Response(202, json={"state": "rendering"})
        return httpx.Response(404, json={"error": {"code": "not_found"}})

    @property
    def paths(self) -> list[str]:
        return [f"{method} {path}" for method, path, _ in self.requests]

    def client(self, **kwargs: Any) -> Any:
        from xamxam.timalens import TimaLensClient

        async def no_sleep(_: float) -> None:
            return None

        return TimaLensClient(
            "tlak_test", transport=httpx.MockTransport(self.handler), sleep=no_sleep, **kwargs
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


def button_reply(title: str, message_id: str = "wamid.btn") -> dict[str, Any]:
    return {
        "from": STUDENT,
        "id": message_id,
        "timestamp": "1760000003",
        "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "b1", "title": title}},
    }


def tool_results(agent: ScriptedAgentModel, step: int) -> list[dict[str, Any]]:
    """Résultats d'outils reçus par l'agent au début de l'étape `step` (0 = première)."""
    results: list[dict[str, Any]] = []
    for message in reversed(agent.received[step]):
        if message["role"] != "tool":
            break
        results.insert(0, json.loads(message["content"]))
    return results
