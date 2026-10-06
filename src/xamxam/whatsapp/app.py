"""Application FastAPI : webhook WhatsApp Cloud (Meta) et outils de développement.

Lancement local, depuis la racine du dépôt :
    uvicorn --factory xamxam.whatsapp.app:create_app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from xamxam.config import DEFAULT_LEXICON_PATH, Settings
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import ProviderError, ProviderName, TTSProvider, create_tts_provider
from xamxam.whatsapp.bot import XamXamBot
from xamxam.whatsapp.factory import build_bot
from xamxam.whatsapp.payloads import WebhookPayload, extract_messages
from xamxam.whatsapp.settings import BotSettings
from xamxam.whatsapp.signature import SIGNATURE_HEADER, is_valid_signature

logger = logging.getLogger(__name__)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def create_app(
    settings: Settings | None = None,
    *,
    pipeline: XamXamPipeline | None = None,
    tts: TTSProvider | None = None,
    bot: XamXamBot | None = None,
) -> FastAPI:
    """Construit l'application ; les dépendances sont injectables pour les tests."""
    settings = settings or Settings.from_env()
    bot_settings = BotSettings.from_env()
    pipeline = pipeline or XamXamPipeline.from_lexicon_file(
        DEFAULT_LEXICON_PATH, number_language=bot_settings.number_language
    )
    tts = tts or create_tts_provider(ProviderName.AUTO, settings)
    missing = [] if bot is not None else settings.missing_bot_variables()
    if bot is None and not missing:
        bot = build_bot(settings, pipeline, bot_settings)
    if bot is None:
        logger.warning("Bot WhatsApp désactivé, variables manquantes : %s", ", ".join(missing))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if bot is not None:
            await bot.drain()

    app = FastAPI(title="Xam-Xam", summary="Narration scientifique en wolof", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "tts": tts.name,
            "bot_ready": bot is not None,
            "llm": bot.llm_info if bot is not None else None,
            "missing_variables": missing,
        }

    @app.get("/webhook", response_class=PlainTextResponse)
    def verify_webhook(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ) -> str:
        """Vérification de l'abonnement par Meta : renvoyer le challenge si le jeton correspond."""
        expected = settings.whatsapp_verify_token
        if mode == "subscribe" and expected and token == expected:
            return challenge
        raise HTTPException(status_code=403, detail="Jeton de vérification invalide.")

    @app.post("/webhook")
    async def receive_webhook(request: Request) -> dict[str, str]:
        """Répond 200 immédiatement ; le traitement se fait en tâche de fond."""
        if bot is None or not settings.whatsapp_app_secret:
            raise HTTPException(status_code=503, detail="Bot WhatsApp non configuré.")
        body = await request.body()
        if not is_valid_signature(
            body, request.headers.get(SIGNATURE_HEADER), settings.whatsapp_app_secret
        ):
            raise HTTPException(status_code=401, detail="Signature invalide.")
        try:
            payload = WebhookPayload.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="Notification illisible.") from exc
        for message in extract_messages(payload):
            await bot.receive(message)
        return {"status": "received"}

    @app.post("/dev/speak", response_class=Response)
    def speak(body: SpeakRequest) -> Response:
        """Outil de développement : texte → audio, après passage par Xam-Xam."""
        prepared = pipeline.prepare(body.text)
        try:
            audio = tts.synthesize(prepared.text)
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return Response(content=audio, media_type="audio/wav")

    return app
