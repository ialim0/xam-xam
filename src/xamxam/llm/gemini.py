"""Implémentation Gemini (SDK google-genai).

Le modèle n'est jamais codé en dur : il vient de GEMINI_MODEL.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from xamxam.config import Settings
from xamxam.llm.base import LLMError, LLMProvider, ProblemInput
from xamxam.llm.prompts import build_system_prompt, build_user_prompt
from xamxam.llm.schema import MathSolution, solution_json_schema
from xamxam.metrics import record_request

DEFAULT_TEMPERATURE = 0.2


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        lexicon_terms: Iterable[str],
        max_explanation_chars: int,
        client: Any | None = None,
    ) -> None:
        if not api_key or not model:
            raise LLMError("Gemini non configuré : définissez GEMINI_API_KEY et GEMINI_MODEL.")
        if client is None:
            from google import genai  # import tardif : inutile sans clé

            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model
        self._system_prompt = build_system_prompt(lexicon_terms, max_explanation_chars)
        self._schema = solution_json_schema()

    @classmethod
    def from_settings(
        cls, settings: Settings, *, lexicon_terms: Iterable[str], max_explanation_chars: int
    ) -> GeminiProvider:
        return cls(
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_model or "",
            lexicon_terms=lexicon_terms,
            max_explanation_chars=max_explanation_chars,
        )

    def __repr__(self) -> str:
        return f"GeminiProvider(model={self._model!r})"

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def solve(self, problem: ProblemInput) -> MathSolution:
        from google.genai import types

        if problem.is_empty:
            raise LLMError("Rien à analyser : ni image, ni transcription, ni texte.")
        contents: list[Any] = []
        if problem.image:
            contents.append(
                types.Part.from_bytes(
                    data=problem.image, mime_type=problem.image_mime_type or "image/jpeg"
                )
            )
        contents.append(build_user_prompt(problem))
        config = types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            response_mime_type="application/json",
            response_json_schema=self._schema,
            temperature=DEFAULT_TEMPERATURE,
        )
        record_request("gemini")
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except Exception as exc:  # le SDK lève des exceptions variées selon l'erreur réseau/API
            # Le message d'origine peut citer la requête : seul le type est gardé.
            raise LLMError(f"Appel Gemini impossible ({type(exc).__name__}).") from exc
        try:
            return MathSolution.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise LLMError(
                f"Réponse Gemini non conforme au schéma ({exc.error_count()} erreur(s))."
            ) from exc
