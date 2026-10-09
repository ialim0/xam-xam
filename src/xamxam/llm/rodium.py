"""Client RodiumAI compatible avec l'API OpenAI Chat Completions."""

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

RODIUM_BASE_URL = "https://api.rodiumai.io/v1"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RodiumHTTP:
    """Appels Rodium avec réessais courts et repli de modèle optionnel."""

    def __init__(
        self,
        *,
        api_key: str,
        models: Sequence[str],
        base_url: str = RODIUM_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.models = list(dict.fromkeys(m for m in models if m))
        if not api_key or not self.models:
            raise LLMError("Rodium non configuré : définissez RODIUM_API_KEY.")
        self._http = httpx.Client(
            timeout=timeout,
            transport=transport,
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._sleep = sleep

    def __repr__(self) -> str:
        return f"RodiumHTTP(models={self.models!r})"

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = 0
        for model_index, model in enumerate(self.models):
            if model_index:
                logger.warning(
                    "Rodium %s indisponible (%d) : repli sur %s.",
                    self.models[model_index - 1],
                    status,
                    model,
                )
            body = {**payload, "model": model, "stream": False}
            for attempt in range(2):
                if attempt:
                    self._sleep(1.0)
                record_request("rodium")
                try:
                    response = self._http.post("chat/completions", json=body)
                except httpx.TimeoutException:
                    status = 504
                    break
                except httpx.HTTPError as exc:
                    raise LLMError(f"API Rodium injoignable ({type(exc).__name__}).") from exc
                status = response.status_code
                if not response.is_error:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise LLMError("Réponse de Rodium illisible.") from exc
                    return data if isinstance(data, dict) else {}
                if status not in RETRYABLE_STATUSES:
                    if status in {400, 404} and model_index + 1 < len(self.models):
                        break
                    raise LLMError(f"API Rodium : erreur {status}.")
        raise LLMError(f"API Rodium : erreur {status}.")


class RodiumProvider(LLMProvider):
    name = "rodium"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        fallback_models: Sequence[str] = (),
        base_url: str = RODIUM_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
        temperature: float = 0.2,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self._rodium = RodiumHTTP(
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
        return f"RodiumProvider(model={self.model!r})"

    def generate(self, problem: ProblemInput) -> LLMResult:
        if problem.is_empty:
            raise LLMError("Rien à analyser : ni image, ni transcription, ni texte.")
        start = self._clock()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._user_content(problem)},
        ]
        input_tokens = output_tokens = 0
        for attempt in (1, 2):
            data = self._rodium.post(
                {"messages": messages, "max_tokens": 4096, "temperature": self._temperature}
            )
            text = self._response_text(data)
            usage = data.get("usage") or {}
            input_tokens += int(usage.get("prompt_tokens") or 0)
            output_tokens += int(usage.get("completion_tokens") or 0)
            try:
                solution = parse_solution_text(text)
                break
            except InvalidStructuredOutputError as exc:
                if attempt == 2:
                    raise InvalidStructuredOutputError(
                        f"Réponse de Rodium non conforme après réparation ({exc})."
                    ) from exc
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": REPAIR_INSTRUCTION.format(errors=str(exc))},
                ]
        return LLMResult(
            solution,
            CallStats(
                latency_ms=int((self._clock() - start) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                attempts=attempt,
            ),
        )

    @staticmethod
    def _response_text(data: dict[str, Any]) -> str:
        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError("Réponse de Rodium illisible (aucun choix).") from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        raise LLMError("Réponse de Rodium illisible (contenu non textuel).")

    @staticmethod
    def _user_content(problem: ProblemInput) -> str | list[dict[str, Any]]:
        prompt = build_user_prompt(problem)
        if not problem.image:
            return prompt
        mime = (problem.image_mime_type or "image/jpeg").split(";")[0].strip().lower()
        if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise LLMError(f"Format d'image non pris en charge par Rodium : {mime}.")
        url = f"data:{mime};base64,{base64.b64encode(problem.image).decode('ascii')}"
        return [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]
