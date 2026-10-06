"""Provider auto-hébergé : tout serveur exposant l'API compatible OpenAI (vLLM, Ollama…).

L'image est envoyée en data URL ; la sortie est contrainte par response_format
(json_schema), puis validée par pydantic, avec une seule tentative de réparation.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any

import httpx

from xamxam.llm.base import CallStats, LLMError, LLMProvider, LLMResult, ProblemInput
from xamxam.llm.prompts import build_user_prompt
from xamxam.llm.schema import solution_json_schema
from xamxam.llm.structured import (
    REPAIR_INSTRUCTION,
    TOOL_NAME,
    InvalidStructuredOutputError,
    parse_solution_text,
)
from xamxam.metrics import record_request

DEFAULT_TIMEOUT = 120.0
DEFAULT_TEMPERATURE = 0.2


class OpenAICompatibleProvider(LLMProvider):
    name = "selfhosted"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = DEFAULT_TEMPERATURE,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not base_url or not model:
            raise LLMError(
                "Serveur auto-hébergé non configuré : définissez SELFHOSTED_BASE_URL et "
                "SELFHOSTED_MODEL."
            )
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(timeout=timeout, transport=transport, headers=headers)
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._clock = clock

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(url={self._url!r}, model={self.model!r})"

    def generate(self, problem: ProblemInput) -> LLMResult:
        if problem.is_empty:
            raise LLMError("Rien à analyser : ni image, ni transcription, ni texte.")
        start = self._clock()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._user_content(problem)},
        ]
        usage = [0, 0]
        attempts = 0
        for attempt in (1, 2):
            attempts = attempt
            text = self._complete(messages, usage)
            try:
                solution = parse_solution_text(text)
                break
            except InvalidStructuredOutputError as exc:
                if attempt == 2:
                    raise InvalidStructuredOutputError(
                        f"Réponse du serveur non conforme après réparation ({exc})."
                    ) from exc
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": REPAIR_INSTRUCTION.format(errors=str(exc))},
                ]
        stats = CallStats(
            latency_ms=int((self._clock() - start) * 1000),
            input_tokens=usage[0],
            output_tokens=usage[1],
            attempts=attempts,
        )
        return LLMResult(solution, stats)

    def _user_content(self, problem: ProblemInput) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if problem.image:
            mime = (problem.image_mime_type or "image/jpeg").split(";")[0].strip()
            encoded = base64.b64encode(problem.image).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
            )
        content.append({"type": "text", "text": build_user_prompt(problem)})
        return content

    def _complete(self, messages: list[dict[str, Any]], usage: list[int]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            # Décodage guidé par le schéma (vLLM, Ollama) : JSON valide dès le premier essai.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": TOOL_NAME, "schema": solution_json_schema()},
            },
        }
        record_request("selfhosted")
        try:
            response = self._http.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Serveur LLM injoignable ({type(exc).__name__}).") from exc
        if response.is_error:
            # Le corps d'erreur peut citer la requête : seul le statut est gardé.
            raise LLMError(f"Serveur LLM : erreur {response.status_code}.")
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Réponse du serveur LLM illisible.") from exc
        tokens = data.get("usage") or {}
        usage[0] += int(tokens.get("prompt_tokens") or 0)
        usage[1] += int(tokens.get("completion_tokens") or 0)
        return text
