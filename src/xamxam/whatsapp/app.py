"""Webhook FastAPI du bot WhatsApp.

Squelette : la réception réelle des messages (image d'exercice, note vocale) et
l'envoi de la réponse audio restent à implémenter (voir les TODO).

Lancement local, depuis la racine du dépôt :
    uvicorn --factory xamxam.whatsapp.app:create_app --reload
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from xamxam.config import DEFAULT_LEXICON_PATH, Settings
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import ProviderError, ProviderName, TTSProvider, create_tts_provider
from xamxam.timalens import build_timalens_client


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def handle_image(image: bytes) -> bytes:
    """Photo d'exercice → explication audio en wolof."""
    # TODO : OCR de l'exercice, génération de l'explication, passage par Xam-Xam puis TTS.
    raise NotImplementedError("Traitement des images pas encore implémenté.")


def handle_voice_note(audio: bytes) -> bytes:
    """Question vocale de l'élève → réponse audio en wolof."""
    # TODO : STT de la question, génération de la réponse, passage par Xam-Xam puis TTS.
    raise NotImplementedError("Traitement des notes vocales pas encore implémenté.")


def create_app(
    settings: Settings | None = None,
    *,
    pipeline: XamXamPipeline | None = None,
    tts: TTSProvider | None = None,
) -> FastAPI:
    """Construit l'application ; les dépendances sont injectables pour les tests."""
    settings = settings or Settings.from_env()
    pipeline = pipeline or XamXamPipeline.from_lexicon_file(DEFAULT_LEXICON_PATH)
    tts = tts or create_tts_provider(ProviderName.AUTO, settings)
    video_client = build_timalens_client(settings)

    app = FastAPI(title="Xam-Xam", summary="Narration scientifique en wolof")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "tts": tts.name,
            "whatsapp_enabled": settings.whatsapp_token is not None,
            "video_enabled": video_client is not None,
        }

    @app.post("/webhook")
    async def receive_message(request: Request) -> dict[str, str]:
        if settings.whatsapp_token is None:
            raise HTTPException(
                status_code=503, detail="WhatsApp non configuré : WHATSAPP_TOKEN absent."
            )
        await request.json()
        # TODO : choisir le fournisseur WhatsApp (API Cloud de Meta, Twilio…) puis :
        #   1. vérifier la signature / le jeton de la requête ;
        #   2. identifier le type de message (image ou note vocale) et télécharger le média ;
        #   3. appeler handle_image() ou handle_voice_note() ;
        #   4. renvoyer l'audio à l'élève et, si video_client existe, un lien vers un clip.
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
