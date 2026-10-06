"""Assemblage du bot à partir de la configuration."""

from __future__ import annotations

import os

from xamxam.config import Settings
from xamxam.llm.gemini import GeminiProvider
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import (
    CachedSTTProvider,
    CachedTTSProvider,
    ProviderName,
    RateLimiter,
    create_providers,
)
from xamxam.whatsapp.bot import XamXamBot
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.meta import MetaClient
from xamxam.whatsapp.privacy import IdHasher
from xamxam.whatsapp.settings import BotSettings


def build_bot(
    settings: Settings, pipeline: XamXamPipeline, bot_settings: BotSettings | None = None
) -> XamXamBot:
    """Construit le bot réel (Meta, Gemini, Kiriku). Suppose missing_bot_variables() vide."""
    bot_settings = bot_settings or BotSettings.from_env()
    messages_path = os.environ.get("XAMXAM_MESSAGES_PATH", "").strip()
    messages = BotMessages.from_json_file(messages_path) if messages_path else BotMessages()

    # Un seul limiteur pour tout le processus : le quota Kiriku est partagé TTS + STT.
    limiter = RateLimiter(bot_settings.kiriku_requests_per_minute)
    tts, stt = create_providers(ProviderName.AUTO, settings, limiter=limiter)
    return XamXamBot(
        meta=MetaClient(
            token=settings.whatsapp_token or "",
            phone_number_id=settings.whatsapp_phone_number_id or "",
            api_version=settings.whatsapp_graph_api_version,
        ),
        llm=GeminiProvider.from_settings(
            settings,
            lexicon_terms=[term.term for term in pipeline.index.lexicon.terms],
            max_explanation_chars=bot_settings.max_explanation_chars,
        ),
        stt=CachedSTTProvider(stt, settings.cache_dir / "stt"),
        tts=CachedTTSProvider(tts, settings.cache_dir / "tts"),
        pipeline=pipeline,
        kiriku_limiter=limiter,
        hasher=IdHasher(settings.log_hash_key),
        settings=bot_settings,
        messages=messages,
        unlimited_numbers=settings.unlimited_numbers,
    )
