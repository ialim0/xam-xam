"""Construction du modèle de langage à partir de la configuration."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import httpx

from xamxam.config import Settings
from xamxam.llm.base import LLMConfigurationError, LLMProvider
from xamxam.llm.gemini import GeminiProvider
from xamxam.llm.prompts import build_system_prompt
from xamxam.llm.rodium import RodiumProvider


def build_llm(
    model: str,
    *,
    api_key: str,
    fallback_models: Sequence[str] = (),
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    translate_from_french: bool = False,
    http_transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Crée le provider Gemini direct pour les anciens déploiements."""
    if not api_key:
        raise LLMConfigurationError("GEMINI_API_KEY n'est pas définie (voir README).")
    prompt = build_system_prompt(
        lexicon_terms,
        max_explanation_chars,
        translate_from_french=translate_from_french,
        # Gemini reçoit seulement responseMimeType : le schéma est donné dans le prompt.
        include_schema=True,
    )
    return GeminiProvider(
        api_key=api_key,
        model=model,
        system_prompt=prompt,
        fallback_models=fallback_models,
        transport=http_transport,
    )


def build_rodium_llm(
    model: str,
    *,
    api_key: str,
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    translate_from_french: bool = False,
    http_transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Crée un modèle Rodium pour les benchmarks et la sélection explicite de modèles."""
    if not api_key:
        raise LLMConfigurationError("RODIUM_API_KEY n'est pas définie (voir README).")
    prompt = build_system_prompt(
        lexicon_terms,
        max_explanation_chars,
        translate_from_french=translate_from_french,
        include_schema=True,
    )
    return RodiumProvider(
        api_key=api_key,
        model=model,
        system_prompt=prompt,
        transport=http_transport,
    )


def create_llm(
    settings: Settings,
    *,
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    http_transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Privilégie Rodium ; conserve Gemini comme compatibilité pour les anciens déploiements."""
    if settings.rodium_api_key:
        prompt = build_system_prompt(
            lexicon_terms,
            max_explanation_chars,
            translate_from_french=settings.translate_from_french,
            include_schema=True,
        )
        return RodiumProvider(
            api_key=settings.rodium_api_key,
            model=settings.rodium_model,
            fallback_models=[settings.rodium_fallback_model],
            system_prompt=prompt,
            transport=http_transport,
        )
    return build_llm(
        settings.gemini_model,
        api_key=settings.gemini_api_key or "",
        fallback_models=[settings.gemini_fallback_model],
        lexicon_terms=lexicon_terms,
        max_explanation_chars=max_explanation_chars,
        translate_from_french=settings.translate_from_french,
        http_transport=http_transport,
    )
