"""Provider Amazon Bedrock, via l'API Converse (image + texte, sortie JSON validée).

Le modèle (BEDROCK_MODEL_ID) et la région (BEDROCK_REGION) viennent de la configuration.
Pour les modèles qui supportent l'appel d'outils, le JSON est forcé par un outil dont le
schéma d'entrée est celui de la solution ; sinon, le schéma est donné dans le prompt et une
seule tentative de réparation est faite si la réponse n'est pas conforme.

Le SDK AWS (boto3) est une dépendance optionnelle : `pip install "xamxam[bedrock]"`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from xamxam.llm.base import CallStats, LLMError, LLMProvider, LLMResult, ProblemInput
from xamxam.llm.prompts import build_user_prompt
from xamxam.llm.schema import solution_json_schema
from xamxam.llm.structured import (
    REPAIR_INSTRUCTION,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    InvalidStructuredOutputError,
    parse_solution_object,
    parse_solution_text,
)
from xamxam.metrics import record_request

# Formats d'image acceptés par le bloc « image » de Converse.
IMAGE_FORMATS = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.2


def create_bedrock_client(region: str) -> Any:
    try:
        import boto3  # import tardif : seul le provider Bedrock dépend du SDK AWS
    except ImportError as exc:
        raise LLMError(
            'boto3 est absent : installez l\'extra « bedrock » (pip install "xamxam[bedrock]").'
        ) from exc
    return boto3.client("bedrock-runtime", region_name=region)


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(
        self,
        *,
        model_id: str,
        region: str,
        system_prompt: str,
        supports_tool_use: bool,
        client: Any | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not model_id or not region:
            raise LLMError("Bedrock non configuré : définissez BEDROCK_MODEL_ID et BEDROCK_REGION.")
        self.model = model_id
        self.region = region
        self._client = client if client is not None else create_bedrock_client(region)
        self._system_prompt = system_prompt
        self._use_tool = supports_tool_use
        self._inference = {"maxTokens": max_tokens, "temperature": temperature}
        self._clock = clock

    def __repr__(self) -> str:
        return f"BedrockProvider(model={self.model!r}, region={self.region!r})"

    def generate(self, problem: ProblemInput) -> LLMResult:
        if problem.is_empty:
            raise LLMError("Rien à analyser : ni image, ni transcription, ni texte.")
        start = self._clock()
        messages: list[dict[str, Any]] = [{"role": "user", "content": self._user_content(problem)}]
        usage = [0, 0]
        attempts = 0
        for attempt in (1, 2):
            attempts = attempt
            response = self._converse(messages, usage)
            message = response.get("output", {}).get("message", {})
            try:
                solution = self._parse(message)
                break
            except InvalidStructuredOutputError as exc:
                if attempt == 2:
                    raise InvalidStructuredOutputError(
                        f"Réponse Bedrock non conforme après réparation ({exc})."
                    ) from exc
                messages += self._repair_turn(message, str(exc))
        stats = CallStats(
            latency_ms=int((self._clock() - start) * 1000),
            input_tokens=usage[0],
            output_tokens=usage[1],
            attempts=attempts,
            used_tool=self._use_tool,
        )
        return LLMResult(solution, stats)

    # --- Construction des requêtes --------------------------------------------------

    def _user_content(self, problem: ProblemInput) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if problem.image:
            mime = (problem.image_mime_type or "image/jpeg").split(";")[0].strip().lower()
            image_format = IMAGE_FORMATS.get(mime)
            if image_format is None:
                raise LLMError(f"Format d'image non accepté par Bedrock : {mime}.")
            content.append({"image": {"format": image_format, "source": {"bytes": problem.image}}})
        content.append({"text": build_user_prompt(problem)})
        return content

    def _converse(self, messages: list[dict[str, Any]], usage: list[int]) -> dict[str, Any]:
        request: dict[str, Any] = {
            "modelId": self.model,
            "system": [{"text": self._system_prompt}],
            "messages": messages,
            "inferenceConfig": self._inference,
        }
        if self._use_tool:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": TOOL_NAME,
                            "description": TOOL_DESCRIPTION,
                            "inputSchema": {"json": solution_json_schema()},
                        }
                    }
                ],
                # Appel d'outil obligatoire : la réponse est forcément l'objet structuré.
                "toolChoice": {"tool": {"name": TOOL_NAME}},
            }
        record_request("bedrock")
        try:
            response = self._client.converse(**request)
        except Exception as exc:  # erreurs botocore variées ; leur message peut citer la requête
            raise LLMError(f"Appel Bedrock impossible ({type(exc).__name__}).") from exc
        tokens = response.get("usage", {})
        usage[0] += int(tokens.get("inputTokens", 0))
        usage[1] += int(tokens.get("outputTokens", 0))
        return response

    def _parse(self, message: dict[str, Any]):  # type: ignore[no-untyped-def]
        blocks = message.get("content", [])
        if self._use_tool:
            for block in blocks:
                tool_use = block.get("toolUse")
                if tool_use and tool_use.get("name") == TOOL_NAME:
                    return parse_solution_object(tool_use.get("input"))
            raise InvalidStructuredOutputError("aucun appel d'outil dans la réponse")
        text = "".join(block.get("text", "") for block in blocks)
        return parse_solution_text(text)

    def _repair_turn(self, message: dict[str, Any], errors: str) -> list[dict[str, Any]]:
        instruction = REPAIR_INSTRUCTION.format(errors=errors)
        assistant = {"role": "assistant", "content": message.get("content", [])}
        tool_use = next((b["toolUse"] for b in assistant["content"] if "toolUse" in b), None)
        if tool_use is not None:
            # Après un appel d'outil, Converse attend un résultat d'outil (ici en erreur).
            result = {
                "toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"text": instruction}],
                    "status": "error",
                }
            }
            return [assistant, {"role": "user", "content": [result]}]
        return [assistant, {"role": "user", "content": [{"text": instruction}]}]
