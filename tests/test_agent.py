import json
from typing import Any

import httpx
import pytest

from fakes import button_reply, image_message, make_solution, webhook_payload
from xamxam.agent import (
    TOOL_DECLARATIONS,
    AgentState,
    ConversationMemory,
    GeminiAgentModel,
    build_agent_prompt,
    history_messages,
    run_agent,
)
from xamxam.agent.memory import STUDENT, TUTOR
from xamxam.agent.model import calls, to_gemini_contents, tool_message
from xamxam.agent.prompt import SOLVE
from xamxam.errors import XamXamError
from xamxam.llm import LLMError
from xamxam.whatsapp.payloads import MessageKind, WebhookPayload, extract_messages

# --- Modèle Gemini (appel de fonctions) -----------------------------------------------------


def _gemini(handler) -> GeminiAgentModel:
    return GeminiAgentModel(
        api_key="g-secret",
        model="gemini-3.5-flash",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )


def _reply(*parts: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": list(parts)}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 7},
        },
    )


def test_gemini_agent_sends_tools_and_parses_calls() -> None:
    requests: list[httpx.Request] = []
    signed_call = {
        "functionCall": {"name": SOLVE, "args": {"question": "BC ?"}, "id": "c1"},
        "thoughtSignature": "sig-123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _reply({"text": "je réfléchis", "thought": True}, signed_call)

    turn = _gemini(handler).next_turn(
        "système", [{"role": "user", "content": "BC ?"}], TOOL_DECLARATIONS
    )

    [request] = requests
    assert request.headers["x-goog-api-key"] == "g-secret"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "système"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "BC ?"}]}]
    assert body["tools"] == [{"functionDeclarations": TOOL_DECLARATIONS}]
    assert body["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"
    [tool_call] = turn.calls
    assert (tool_call.name, tool_call.args, tool_call.call_id) == (
        SOLVE,
        {"question": "BC ?"},
        "c1",
    )
    assert turn.text == ""  # la pensée n'est pas une réponse
    assert (turn.input_tokens, turn.output_tokens) == (50, 7)
    # Les parties brutes, signature comprise, sont gardées pour être renvoyées au modèle.
    assert turn.message["gemini_parts"][1]["thoughtSignature"] == "sig-123"


def test_gemini_agent_errors_hide_content_and_key() -> None:
    with pytest.raises(LLMError, match="erreur 400") as raised:
        _gemini(lambda r: httpx.Response(400, text="élève: secret")).next_turn("s", [], [])
    assert "secret" not in str(raised.value)
    with pytest.raises(LLMError, match="aucun candidat"):
        _gemini(lambda r: httpx.Response(200, json={})).next_turn("s", [], [])
    assert "g-secret" not in repr(_gemini(lambda r: _reply()))


def test_history_is_converted_to_gemini_contents() -> None:
    solve_args, ok = {"question": "BC ?"}, {"statut": "ok"}
    scripted = calls((SOLVE, solve_args))
    messages = [
        {"role": "user", "content": "salut"},
        {"role": "assistant", "content": "Maa ngi fi."},
        {"role": "user", "content": "BC ?"},
        scripted.message,
        tool_message(scripted.calls[0], {"statut": "ok"}),
    ]
    assert to_gemini_contents(messages) == [
        {"role": "user", "parts": [{"text": "salut"}]},
        {"role": "model", "parts": [{"text": "Maa ngi fi."}]},
        {"role": "user", "parts": [{"text": "BC ?"}]},
        {"role": "model", "parts": [{"functionCall": {"name": SOLVE, "args": solve_args}}]},
        # Identifiant créé localement : il n'est pas renvoyé à Gemini.
        {"role": "user", "parts": [{"functionResponse": {"name": SOLVE, "response": ok}}]},
    ]


def test_every_tool_declaration_is_well_formed() -> None:
    names = [tool["name"] for tool in TOOL_DECLARATIONS]
    assert len(names) == len(set(names)) == 5
    for tool in TOOL_DECLARATIONS:
        parameters = tool["parameters"]
        assert tool["description"] and parameters["type"] == "object"
        assert set(parameters["required"]) <= set(parameters["properties"])


# --- Boucle --------------------------------------------------------------------------------


class _Toolbox:
    declarations = TOOL_DECLARATIONS

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self.said: list[str] = []

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.executed.append((name, args))
        if name == "casse":
            raise XamXamError("contenu de l'élève")
        return {"statut": "ok"}

    async def say(self, text: str) -> None:
        self.said.append(text)


@pytest.mark.anyio
async def test_loop_returns_signed_calls_with_their_results() -> None:
    requests: list[dict[str, Any]] = []
    replies = iter(
        [
            _reply(
                {"functionCall": {"name": SOLVE, "args": {}, "id": "c1"}, "thoughtSignature": "s"},
                {"functionCall": {"name": "casse", "args": {}}},
            ),
            _reply({"text": "Tontu bi : 5 cm"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return next(replies)

    toolbox = _Toolbox()
    run = await run_agent(
        _gemini(handler),
        system="s",
        messages=[{"role": "user", "content": "BC ?"}],
        toolbox=toolbox,
    )

    assert run.steps == 2 and run.tools == [SOLVE, "casse"]
    assert toolbox.said == ["Tontu bi : 5 cm"]
    _, model_turn, results = requests[1]["contents"]
    assert model_turn["parts"][0]["thoughtSignature"] == "s"  # renvoyée telle quelle
    assert results == {
        "role": "user",
        "parts": [
            {"functionResponse": {"name": SOLVE, "response": {"statut": "ok"}, "id": "c1"}},
            {
                "functionResponse": {
                    "name": "casse",
                    "response": {"statut": "erreur", "detail": "XamXamError"},
                }
            },
        ],
    }


# --- Mémoire et consignes ----------------------------------------------------------------------


def test_memory_expires_and_keeps_alternating_roles() -> None:
    now = [0.0]
    memory = ConversationMemory(ttl_seconds=60, max_turns=4, clock=lambda: now[0])
    conversation = memory.get("u1")
    conversation.note(TUTOR, "message orphelin")
    conversation.note(STUDENT, "salut")
    conversation.note(STUDENT, "[photo de l'exercice jointe]")
    conversation.note(TUTOR, "Tontu bi : 5 cm")
    messages = history_messages(conversation)
    assert [m["role"] for m in messages] == ["user", "assistant"]  # commence par l'élève
    assert messages[0]["content"] == "salut\n[photo de l'exercice jointe]"

    now[0] = 30
    assert memory.get("u1") is conversation
    now[0] = 100  # 70 s d'inactivité
    fresh = memory.get("u1")
    assert fresh is not conversation and not fresh.turns

    fresh.video_in_progress = True  # une vidéo en cours garde la conversation
    now[0] = 1000
    memory.get("u2")
    assert len(memory) == 2


def test_prompt_describes_the_state() -> None:
    state = AgentState(
        voice=True,
        video=True,
        videos_left_today=3,
        video_in_progress=False,
        audio_count=1,
        exercise="ABC rectangle en A → BC = 5 cm",
    )
    prompt = build_agent_prompt(state, max_chars=800)
    assert "disponible (3 restante(s) aujourd'hui)" in prompt
    assert "Notes vocales envoyées pour l'exercice en cours : 1." in prompt
    assert "ABC rectangle en A → BC = 5 cm" in prompt and "800" in prompt
    assert "Ne donne jamais un résultat chiffré qui ne vient pas de resoudre_exercice" in prompt
    busy = build_agent_prompt(AgentState(False, True, 0, True, 0, None), max_chars=800)
    assert "une vidéo est déjà en préparation" in busy and "indisponible" in busy
    assert make_solution()  # le schéma de solution reste importable avec l'agent


# --- WhatsApp : boutons et légendes ----------------------------------------------------------


def test_button_clicks_and_photo_captions_become_text() -> None:
    photo = image_message()
    photo["image"]["caption"] = "question 2"
    sticker = {"from": "1", "id": "s", "type": "sticker", "sticker": {"id": "x"}}
    payload = WebhookPayload.model_validate(
        webhook_payload(button_reply("🔊 Écouter"), photo, sticker)
    )
    button, image, other = extract_messages(payload)
    assert (button.kind, button.text) == (MessageKind.TEXT, "🔊 Écouter")
    assert (image.kind, image.text, image.media_id) == (MessageKind.IMAGE, "question 2", "img-1")
    assert other.kind is MessageKind.OTHER and other.text is None
