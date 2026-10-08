"""Provider Gemini (API Google AI Studio) : la photo est envoyée telle quelle au modèle.

Appel REST `models/{modèle}:generateContent`, image en `inline_data` (base64), réponse JSON
imposée par `responseMimeType`, schéma rappelé dans le prompt, puis validée par pydantic
avec une seule réparation.

GeminiHTTP réessaie brièvement les erreurs temporaires (429, 5xx, délai dépassé), passe au
modèle de repli, et écarte quelques minutes un modèle saturé (disjoncteur).
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from xamxam.llm.base import CallStats, LLMError, LLMProvider, LLMResult, ProblemInput
from xamxam.llm.prompts import build_user_prompt
from xamxam.llm.structured import (
    REPAIR_INSTRUCTION,
    InvalidStructuredOutputError,
    parse_solution_text,
)
from xamxam.metrics import record_request

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 120.0
DEFAULT_TEMPERATURE = 0.2
# Formats d'image acceptés par Gemini ; WhatsApp envoie du JPEG ou du PNG.
SUPPORTED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
)
# Quota, saturation (« high demand »), erreur interne : temporaires, on réessaie.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503})


class GeminiHTTP:
    """Appels `generateContent` avec réessais courts, puis repli sur les modèles suivants."""

    def __init__(
        self,
        *,
        api_key: str,
        models: Sequence[str],
        base_url: str = GEMINI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        attempts_per_model: int = 2,
        cooldown_seconds: float = 300.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        models = [m for m in dict.fromkeys(models) if m]
        if not api_key or not models:
            raise LLMError("Gemini non configuré : définissez GEMINI_API_KEY.")
        self.models = models
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            timeout=timeout, transport=transport, headers={"x-goog-api-key": api_key}
        )
        self._attempts = attempts_per_model
        self._sleep = sleep
        self._clock = clock
        # Disjoncteur : un modèle saturé est écarté un moment, sans attendre à chaque appel.
        self._cooldown = cooldown_seconds
        self._unavailable_until: dict[str, float] = {}

    def __repr__(self) -> str:
        # Ne jamais afficher la clé.
        return f"GeminiHTTP(models={self.models!r})"

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Envoie `payload` au premier modèle disponible."""
        status = 0
        now = self._clock()
        available = [m for m in self.models if self._unavailable_until.get(m, 0.0) <= now]
        previous = ""
        # Le dernier modèle est toujours tenté, même s'il a échoué récemment.
        for model in available or self.models[-1:]:
            if previous:
                logger.warning(
                    "Gemini %s indisponible (%d) : repli sur %s.", previous, status, model
                )
            previous = model
            url = f"{self._base_url}/models/{model}:generateContent"
            for attempt in range(self._attempts):
                if attempt:
                    self._sleep(float(attempt))
                record_request("gemini")
                try:
                    response = self._http.post(url, json=payload)
                except httpx.TimeoutException:
                    # Modèle saturé qui ne répond plus : on passe directement au suivant.
                    status = 504
                    break
                except httpx.HTTPError as exc:
                    raise LLMError(f"API Gemini injoignable ({type(exc).__name__}).") from exc
                status = response.status_code
                if not response.is_error:
                    self._unavailable_until.pop(model, None)
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise LLMError("Réponse de Gemini illisible.") from exc
                    return data if isinstance(data, dict) else {}
                if status not in RETRYABLE_STATUSES:
                    # Le corps d'erreur peut citer la requête : seul le statut est gardé.
                    raise LLMError(f"API Gemini : erreur {status}.")
            self._unavailable_until[model] = self._clock() + self._cooldown
        raise LLMError(f"API Gemini : erreur {status}.")


def candidate_parts(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parties du premier candidat d'une réponse `generateContent`."""
    try:
        parts = data["candidates"][0]["content"].get("parts") or []
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise LLMError("Réponse de Gemini illisible (aucun candidat).") from exc
    return [p for p in parts if isinstance(p, dict)]


def parts_text(parts: list[dict[str, Any]]) -> str:
    """Texte de la réponse ; les parties « thought » sont le raisonnement interne."""
    return "".join(str(p.get("text", "")) for p in parts if "text" in p and not p.get("thought"))


def usage_tokens(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usageMetadata") or {}
    return int(usage.get("promptTokenCount") or 0), int(usage.get("candidatesTokenCount") or 0)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        fallback_models: Sequence[str] = (),
        base_url: str = GEMINI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = DEFAULT_TEMPERATURE,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._gemini = GeminiHTTP(
            api_key=api_key,
            models=[model, *fallback_models],
            base_url=base_url,
            transport=transport,
            timeout=timeout,
            sleep=sleep,
        )
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._clock = clock

    def __repr__(self) -> str:
        return f"GeminiProvider(model={self.model!r})"

    def generate(self, problem: ProblemInput) -> LLMResult:
        if problem.is_empty:
            raise LLMError("Rien à analyser : ni image, ni transcription, ni texte.")
        start = self._clock()
        contents: list[dict[str, Any]] = [{"role": "user", "parts": self._user_parts(problem)}]
        usage = [0, 0]
        attempts = 0
        for attempt in (1, 2):
            attempts = attempt
            text = self._complete(contents, usage)
            try:
                solution = parse_solution_text(text)
                break
            except InvalidStructuredOutputError as exc:
                if attempt == 2:
                    raise InvalidStructuredOutputError(
                        f"Réponse de Gemini non conforme après réparation ({exc})."
                    ) from exc
                contents += [
                    {"role": "model", "parts": [{"text": text}]},
                    {
                        "role": "user",
                        "parts": [{"text": REPAIR_INSTRUCTION.format(errors=str(exc))}],
                    },
                ]
        stats = CallStats(
            latency_ms=int((self._clock() - start) * 1000),
            input_tokens=usage[0],
            output_tokens=usage[1],
            attempts=attempts,
        )
        return LLMResult(solution, stats)

    def _user_parts(self, problem: ProblemInput) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        if problem.image:
            mime = (problem.image_mime_type or "image/jpeg").split(";")[0].strip().lower()
            if mime not in SUPPORTED_IMAGE_TYPES:
                raise LLMError(f"Format d'image non pris en charge par Gemini : {mime}.")
            encoded = base64.b64encode(problem.image).decode("ascii")
            parts.append({"inline_data": {"mime_type": mime, "data": encoded}})
        parts.append({"text": build_user_prompt(problem)})
        return parts

    def _complete(self, contents: list[dict[str, Any]], usage: list[int]) -> str:
        data = self._gemini.post(
            {
                "systemInstruction": {"parts": [{"text": self._system_prompt}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": self._temperature,
                    "responseMimeType": "application/json",
                },
            }
        )
        text = parts_text(candidate_parts(data))
        tokens = usage_tokens(data)
        usage[0] += tokens[0]
        usage[1] += tokens[1]
        return text
