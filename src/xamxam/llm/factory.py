"""Construction du modèle de langage (Gemini) à partir de la configuration."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import httpx

from xamxam.config import Settings
from xamxam.llm.base import LLMConfigurationError, LLMProvider
from xamxam.llm.gemini import GeminiProvider
from xamxam.llm.prompts import build_system_prompt


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
    """Crée le provider Gemini avec le prompt système de Xam-Xam."""
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


def create_llm(
    settings: Settings,
    *,
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    http_transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Provider configuré par GEMINI_API_KEY, GEMINI_MODEL et GEMINI_FALLBACK_MODEL."""
    return build_llm(
        settings.gemini_model,
        api_key=settings.gemini_api_key or "",
        fallback_models=[settings.gemini_fallback_model],
        lexicon_terms=lexicon_terms,
        max_explanation_chars=max_explanation_chars,
        translate_from_french=settings.translate_from_french,
        http_transport=http_transport,
    )
