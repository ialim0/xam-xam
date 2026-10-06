"""Construction du modèle de langage à partir de la configuration, liste blanche comprise."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from xamxam.config import Settings
from xamxam.llm.allowlist import Allowlist, load_allowlist
from xamxam.llm.base import LLMConfigurationError, LLMProvider
from xamxam.llm.bedrock import BedrockProvider
from xamxam.llm.openai_compatible import OpenAICompatibleProvider
from xamxam.llm.prompts import build_system_prompt


def build_llm(
    provider: str,
    model: str,
    *,
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    region: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    translate_from_french: bool = False,
    allowlist: Allowlist | None = None,
    enforce_allowlist: bool = True,
    bedrock_client: Any | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Crée le provider. Avec `enforce_allowlist`, refuse tout modèle non autorisé."""
    allowlist = allowlist or load_allowlist()
    entry = allowlist.find(provider, model)
    if enforce_allowlist:
        entry = allowlist.require(provider, model, region=region if provider == "bedrock" else None)
    terms = list(lexicon_terms)

    if provider == "bedrock":
        use_tool = bool(entry and entry.supports_tool_use)
        prompt = build_system_prompt(
            terms,
            max_explanation_chars,
            translate_from_french=translate_from_french,
            # Sans appel d'outil, le schéma est donné dans le prompt.
            include_schema=not use_tool,
        )
        return BedrockProvider(
            model_id=model,
            region=region or "",
            system_prompt=prompt,
            supports_tool_use=use_tool,
            client=bedrock_client,
        )
    if provider == "selfhosted":
        prompt = build_system_prompt(
            terms,
            max_explanation_chars,
            translate_from_french=translate_from_french,
            include_schema=True,
        )
        return OpenAICompatibleProvider(
            base_url=base_url or "",
            model=model,
            system_prompt=prompt,
            api_key=api_key,
            transport=http_transport,
        )
    raise LLMConfigurationError(f"LLM_PROVIDER inconnu « {provider} ».")


def create_llm(
    settings: Settings,
    *,
    lexicon_terms: Iterable[str],
    max_explanation_chars: int,
    **overrides: Any,
) -> LLMProvider:
    """Provider actif selon LLM_PROVIDER (bedrock ou selfhosted)."""
    provider = settings.llm_provider or ""
    model = settings.llm_model
    if not model:
        raise LLMConfigurationError("LLM non configuré : voir LLM_PROVIDER et docs/modeles.md.")
    return build_llm(
        provider,
        model,
        lexicon_terms=lexicon_terms,
        max_explanation_chars=max_explanation_chars,
        region=settings.bedrock_region,
        base_url=settings.selfhosted_base_url,
        api_key=settings.selfhosted_api_key,
        translate_from_french=settings.translate_from_french,
        **overrides,
    )
