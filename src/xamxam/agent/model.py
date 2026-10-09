"""Cerveau de l'agent : un modèle qui, à chaque étape, répond ou appelle des outils.

L'historique de l'agent est une liste de messages simples : `user`, `assistant` (avec ses
`tool_calls`) et un message `tool` par résultat d'outil. GeminiAgentModel convertit cet
historique au format Gemini ; RodiumAgentModel l'envoie au format OpenAI Chat Completions.
Les parties brutes de Gemini sont conservées car Gemini 3 exige ses `thoughtSignature`.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from xamxam.llm.base import LLMError
from xamxam.llm.gemini import (
    GEMINI_BASE_URL,
    GeminiHTTP,
    candidate_parts,
    parts_text,
    usage_tokens,
)
from xamxam.llm.rodium import RODIUM_BASE_URL, RodiumHTTP

# Une étape de conversation doit rester rapide ; au-delà, repli sur le modèle suivant.
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""  # identifiant à rappeler dans le résultat
    # Identifiant fourni par le modèle (à lui renvoyer), ou créé localement (à ne pas renvoyer).
    model_id: bool = False


@dataclass(frozen=True)
class ModelTurn:
    """Une réponse du modèle : texte libre et/ou appels d'outils."""

    message: dict[str, Any]  # message `assistant`, à remettre tel quel dans l'historique
    calls: tuple[ToolCall, ...] = ()
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def tool_message(call: ToolCall, result: dict[str, Any]) -> dict[str, Any]:
    """Message `tool` à renvoyer au modèle après l'exécution d'un outil."""
    return {
        "role": "tool",
        "tool_call_id": call.call_id,
        "model_id": call.model_id,
        "name": call.name,
        "content": json.dumps(result, ensure_ascii=False),
    }


class AgentModel(ABC):
    name: str
    model: str

    @abstractmethod
    def next_turn(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        """Une étape de raisonnement : réponse finale ou appels d'outils."""


def to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Historique de l'agent → `contents` Gemini (rôles user / model, appels et résultats)."""
    contents: list[dict[str, Any]] = []

    def add(role: str, parts: list[dict[str, Any]]) -> None:
        if not parts:
            return
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})

    for message in messages:
        role = message["role"]
        if role == "user":
            add("user", [{"text": str(message.get("content", ""))}])
        elif role == "assistant":
            parts = message.get("gemini_parts")
            if parts is None:  # message écrit localement (mémoire, tests)
                parts = [{"text": message["content"]}] if message.get("content") else []
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call["function"]
                    parts.append(
                        {
                            "functionCall": {
                                "name": function["name"],
                                "args": json.loads(function.get("arguments") or "{}"),
                            }
                        }
                    )
            add("model", parts)
        elif role == "tool":
            response: dict[str, Any] = {
                "name": message["name"],
                "response": json.loads(message["content"]),
            }
            if message.get("model_id"):
                response["id"] = message["tool_call_id"]
            add("user", [{"functionResponse": response}])
    return contents


class GeminiAgentModel(AgentModel):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        fallback_models: Sequence[str] = (),
        base_url: str = GEMINI_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
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

    def __repr__(self) -> str:
        return f"GeminiAgentModel(model={self.model!r})"

    def next_turn(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        data = self._gemini.post(
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": to_gemini_contents(messages),
                "tools": [{"functionDeclarations": tools}],
                "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            }
        )
        parts = candidate_parts(data)
        calls = []
        for index, part in enumerate(parts):
            function_call = part.get("functionCall")
            if not isinstance(function_call, dict):
                continue
            model_id = function_call.get("id")
            args = function_call.get("args")
            calls.append(
                ToolCall(
                    name=str(function_call.get("name", "")),
                    args=args if isinstance(args, dict) else {},
                    call_id=str(model_id or f"local-{index}"),
                    model_id=bool(model_id),
                )
            )
        text = parts_text(parts).strip()
        input_tokens, output_tokens = usage_tokens(data)
        return ModelTurn(
            message={
                "role": "assistant",
                "content": text,
                "tool_calls": [_tool_call_entry(c) for c in calls],
                "gemini_parts": parts,
            },
            calls=tuple(calls),
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class RodiumAgentModel(AgentModel):
    """Agent à outils via le format OpenAI Chat Completions de Rodium."""

    name = "rodium"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        fallback_models: Sequence[str] = (),
        base_url: str = RODIUM_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
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

    def __repr__(self) -> str:
        return f"RodiumAgentModel(model={self.model!r})"

    def next_turn(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        history = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id", ""),
                        "content": message.get("content", ""),
                    }
                )
            elif role == "assistant":
                entry = {"role": "assistant", "content": message.get("content", "")}
                if message.get("tool_calls"):
                    entry["tool_calls"] = message["tool_calls"]
                history.append(entry)
            elif role == "user":
                history.append({"role": "user", "content": message.get("content", "")})
        data = self._rodium.post(
            {
                "messages": [{"role": "system", "content": system}, *history],
                "tools": [{"type": "function", "function": declaration} for declaration in tools],
                "tool_choice": "auto",
                "max_tokens": 2048,
            }
        )
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Réponse de Rodium illisible (aucun choix).") from exc
        calls: list[ToolCall] = []
        for item in message.get("tool_calls") or []:
            try:
                function = item["function"]
                raw_args = function.get("arguments") or "{}"
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                if not isinstance(args, dict):
                    args = {}
                calls.append(
                    ToolCall(
                        name=str(function.get("name", "")),
                        args=args,
                        call_id=str(item.get("id", "")),
                        model_id=bool(item.get("id")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise LLMError("Appel d'outil Rodium illisible.") from exc
        text = str(message.get("content") or "").strip()
        usage = data.get("usage") or {}
        return ModelTurn(
            message={
                "role": "assistant",
                "content": text,
                "tool_calls": [_tool_call_entry(call) for call in calls],
            },
            calls=tuple(calls),
            text=text,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


def _tool_call_entry(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.call_id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.args, ensure_ascii=False),
        },
    }


class ScriptedAgentModel(AgentModel):
    """Modèle factice pour les tests : rejoue des étapes préparées et garde ce qu'il reçoit."""

    name = "mock"
    model = "scripted-agent"

    def __init__(self, turns: list[ModelTurn | Exception]) -> None:
        self._turns = list(turns)
        self.received: list[list[dict[str, Any]]] = []
        self.systems: list[str] = []
        self.tools: list[list[str]] = []  # noms des outils proposés à chaque étape

    def next_turn(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        self.systems.append(system)
        self.received.append(list(messages))
        self.tools.append([tool["name"] for tool in tools])
        if not self._turns:
            return say("")  # plus rien de prévu : l'agent s'arrête
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def call(name: str, **args: Any) -> ModelTurn:
    """Étape factice : un appel d'outil (tests)."""
    return calls((name, args))


def calls(*items: tuple[str, dict[str, Any]]) -> ModelTurn:
    """Étape factice : plusieurs appels d'outils dans la même réponse (tests)."""
    parsed = tuple(
        ToolCall(name, dict(args), f"call{index}") for index, (name, args) in enumerate(items)
    )
    return ModelTurn(
        message={
            "role": "assistant",
            "content": "",
            "tool_calls": [_tool_call_entry(c) for c in parsed],
        },
        calls=parsed,
    )


def say(text: str) -> ModelTurn:
    """Étape factice : réponse texte finale (tests)."""
    return ModelTurn(message={"role": "assistant", "content": text}, text=text)
