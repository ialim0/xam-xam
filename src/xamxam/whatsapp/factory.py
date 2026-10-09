"""Assemblage du bot à partir de la configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from xamxam.agent import GeminiAgentModel, RodiumAgentModel
from xamxam.config import Settings
from xamxam.llm.base import LLMConfigurationError
from xamxam.llm.factory import create_llm
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import (
    CachedTTSProvider,
    ProviderName,
    RateLimiter,
    create_providers,
)
from xamxam.timalens import build_timalens_client
from xamxam.whatsapp.bot import XamXamBot
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.meta import MetaClient
from xamxam.whatsapp.privacy import IdHasher
from xamxam.whatsapp.settings import BotSettings

logger = logging.getLogger(__name__)

# « Néggal tuuti » : autocollant animé (WebP 512×512) envoyé pendant chaque traitement.
WAITING_STICKER_PATH = Path(__file__).with_name("assets") / "attente.webp"


def build_bot(
    settings: Settings, pipeline: XamXamPipeline, bot_settings: BotSettings | None = None
) -> XamXamBot:
    """Construit le bot réel : agent Gemini, Meta, Kiriku et TimaLens s'ils sont configurés.
    Suppose missing_bot_variables() vide."""
    if settings.translate_from_french:
        # Aucun modèle de traduction n'est encore choisi.
        raise LLMConfigurationError(
            "TRANSLATE_FROM_FRENCH est activé, mais aucun traducteur n'est configuré."
        )
    bot_settings = bot_settings or BotSettings.from_env()
    messages_path = os.environ.get("XAMXAM_MESSAGES_PATH", "").strip()
    messages = BotMessages.from_json_file(messages_path) if messages_path else BotMessages()

    # Un seul limiteur pour tout le processus : le quota Kiriku est partagé TTS + STT.
    limiter = RateLimiter(bot_settings.kiriku_requests_per_minute)
    tts, stt = None, None
    if settings.kvicc_tts_configured and settings.kvicc_stt_configured:
        tts, stt = create_providers(ProviderName.KVICC, settings, limiter=limiter)
    else:
        # Jamais de mock en production : une fausse note vocale tromperait l'élève.
        logger.warning("Kiriku non configuré : réponses en texte, notes vocales non transcrites.")
    return XamXamBot(
        meta=MetaClient(
            token=settings.whatsapp_token or "",
            phone_number_id=settings.whatsapp_phone_number_id or "",
            api_version=settings.whatsapp_graph_api_version,
        ),
        llm=create_llm(
            settings,
            lexicon_terms=[term.term for term in pipeline.index.lexicon.terms],
            max_explanation_chars=bot_settings.max_explanation_chars,
        ),
        agent=(
            RodiumAgentModel(
                api_key=settings.rodium_api_key,
                model=settings.rodium_model,
                fallback_models=[settings.rodium_fallback_model],
            )
            if settings.rodium_api_key
            else GeminiAgentModel(
                api_key=settings.gemini_api_key or "",
                model=settings.gemini_model,
                fallback_models=[settings.gemini_fallback_model],
            )
        ),
        # Pas de cache STT dans le bot : aucun contenu envoyé par l'élève (photo, audio,
        # transcription) n'est conservé après traitement. Seul le cache TTS (audios
        # d'explication générés) est actif. Le cache STT reste réservé à l'évaluation.
        stt=stt,
        tts=CachedTTSProvider(tts, settings.cache_dir / "tts") if tts is not None else None,
        pipeline=pipeline,
        kiriku_limiter=limiter,
        hasher=IdHasher(settings.log_hash_key),
        settings=bot_settings,
        messages=messages,
        unlimited_numbers=settings.unlimited_numbers,
        state_path=(settings.state_dir or settings.cache_dir) / "bot-state.sqlite3",
        video=build_timalens_client(settings),
        video_voice=settings.timalens_voice,
        video_max_credits=settings.timalens_max_credits,
        waiting_sticker=WAITING_STICKER_PATH.read_bytes() if bot_settings.waiting_sticker else None,
    )
