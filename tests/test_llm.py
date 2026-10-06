import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from fakes import make_solution
from xamxam.config import Settings
from xamxam.llm import LLMConfigurationError, LLMError, MathSolution, ProblemInput
from xamxam.llm.allowlist import load_allowlist
from xamxam.llm.bedrock import BedrockProvider
from xamxam.llm.factory import build_llm, create_llm
from xamxam.llm.openai_compatible import OpenAICompatibleProvider
from xamxam.llm.prompts import build_system_prompt, build_user_prompt
from xamxam.llm.schema import solution_json_schema
from xamxam.llm.structured import (
    TOOL_NAME,
    InvalidStructuredOutputError,
    extract_json_text,
    parse_solution_text,
)

SOLUTION_JSON = make_solution().model_dump_json(by_alias=True)
PROBLEM = ProblemInput(image=b"\xff\xd8photo", image_mime_type="image/jpeg", transcript="naka?")


# --- Schéma et prompts -------------------------------------------------------------------


def test_solution_uses_french_field_names() -> None:
    dumped = json.loads(SOLUTION_JSON)
    assert set(dumped) == {
        "statut", "enonce", "notion", "etapes", "reponse_finale",
        "termes_cles", "explication_wo", "calcul", "explication_fr",
    }  # fmt: skip
    assert MathSolution.model_validate(dumped) == make_solution()
    with pytest.raises(ValidationError):
        MathSolution.model_validate({**dumped, "notion": "algèbre"})


def test_json_schema_is_self_contained() -> None:
    schema = solution_json_schema()
    assert "$ref" not in json.dumps(schema)
    assert {"enonce", "explication_wo", "calcul"} <= set(schema["properties"])


def test_system_prompt_modes() -> None:
    wolof = build_system_prompt(["hypoténuse", "triangle rectangle"], 800)
    assert "hypoténuse, triangle rectangle" in wolof and "800 caractères" in wolof
    assert "Commence toujours par rappeler les données lues" in wolof
    assert "Wolof simple" in wolof and "explication_fr : laisse ce champ vide" in wolof
    assert "schéma" not in wolof.split("Consignes")[-1]

    french = build_system_prompt([], 800, translate_from_french=True, include_schema=True)
    assert "Français simple" in french and "explication_wo : laisse ce champ vide" in french
    assert '"explication_wo"' in french  # schéma JSON inclus


def test_correction_prompt_includes_previous_answer_and_hint() -> None:
    problem = ProblemInput(text="?", previous=make_solution(resultat="7,5"), correction="Corrige.")
    prompt = build_user_prompt(problem)
    assert "Corrige." in prompt and '"resultat":"7,5"' in prompt


# --- Extraction du JSON ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [SOLUTION_JSON, f"```json\n{SOLUTION_JSON}\n```", f"Voici la réponse : {SOLUTION_JSON} Fin."],
)
def test_extract_json_from_text(text: str) -> None:
    assert parse_solution_text(text) == make_solution()


def test_invalid_json_errors_do_not_leak_content() -> None:
    with pytest.raises(InvalidStructuredOutputError, match="aucun objet JSON"):
        extract_json_text("pas de json")
    with pytest.raises(InvalidStructuredOutputError) as raised:
        parse_solution_text('{"statut": "ok", "enonce": "secret de l\'élève"}')
    assert "secret" not in str(raised.value) and "erreur(s)" in str(raised.value)


# --- Bedrock (API Converse) --------------------------------------------------------------


class FakeBedrock:
    """Client bedrock-runtime factice : rejoue des réponses Converse et garde les requêtes."""

    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def converse(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _text_response(text: str, tokens: tuple[int, int] = (100, 50)) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "usage": {"inputTokens": tokens[0], "outputTokens": tokens[1]},
    }


def _tool_response(payload: Any) -> dict[str, Any]:
    block = {"toolUse": {"toolUseId": "t1", "name": TOOL_NAME, "input": payload}}
    return {"output": {"message": {"role": "assistant", "content": [block]}}, "usage": {}}


def _bedrock(client: FakeBedrock, *, tool: bool) -> BedrockProvider:
    return BedrockProvider(
        model_id="mistral.ministral-3-14b-instruct",
        region="eu-west-1",
        system_prompt="prompt système",
        supports_tool_use=tool,
        client=client,
    )


def test_bedrock_converse_request_with_image_and_text() -> None:
    client = FakeBedrock(_text_response(SOLUTION_JSON))
    result = _bedrock(client, tool=False).generate(PROBLEM)

    assert result.solution == make_solution()
    assert (result.stats.input_tokens, result.stats.output_tokens) == (100, 50)
    assert result.stats.json_valid_first_try and not result.stats.used_tool
    [request] = client.requests
    assert request["modelId"] == "mistral.ministral-3-14b-instruct"
    assert request["system"] == [{"text": "prompt système"}]
    image, text = request["messages"][0]["content"]
    assert image == {"image": {"format": "jpeg", "source": {"bytes": b"\xff\xd8photo"}}}
    assert "naka?" in text["text"]
    assert "toolConfig" not in request


def test_bedrock_repairs_invalid_json_once() -> None:
    client = FakeBedrock(_text_response("désolé, voici..."), _text_response(SOLUTION_JSON))
    result = _bedrock(client, tool=False).generate(PROBLEM)
    assert result.solution == make_solution()
    assert result.stats.attempts == 2 and not result.stats.json_valid_first_try
    assert result.stats.input_tokens == 200
    repair = client.requests[1]["messages"]
    assert [m["role"] for m in repair] == ["user", "assistant", "user"]
    assert "n'est pas un objet JSON valide" in repair[-1]["content"][0]["text"]


def test_bedrock_gives_up_after_one_repair() -> None:
    client = FakeBedrock(_text_response("non"), _text_response("toujours non"))
    with pytest.raises(InvalidStructuredOutputError, match="après réparation"):
        _bedrock(client, tool=False).generate(PROBLEM)


def test_bedrock_forces_json_through_tool_use() -> None:
    client = FakeBedrock(_tool_response(json.loads(SOLUTION_JSON)))
    result = _bedrock(client, tool=True).generate(PROBLEM)
    assert result.solution == make_solution() and result.stats.used_tool
    tool_config = client.requests[0]["toolConfig"]
    assert tool_config["toolChoice"] == {"tool": {"name": TOOL_NAME}}
    spec = tool_config["tools"][0]["toolSpec"]
    assert spec["inputSchema"]["json"] == solution_json_schema()


def test_bedrock_tool_repair_uses_tool_result() -> None:
    client = FakeBedrock(
        _tool_response({"statut": "ok"}), _tool_response(json.loads(SOLUTION_JSON))
    )
    assert _bedrock(client, tool=True).generate(PROBLEM).stats.attempts == 2
    reply = client.requests[1]["messages"][-1]["content"][0]["toolResult"]
    assert reply["toolUseId"] == "t1" and reply["status"] == "error"


def test_bedrock_errors_are_wrapped_without_content() -> None:
    client = FakeBedrock(RuntimeError("ThrottlingException: requête de 221771234567"))
    with pytest.raises(LLMError) as raised:
        _bedrock(client, tool=False).generate(PROBLEM)
    assert "221771234567" not in str(raised.value) and "RuntimeError" in str(raised.value)


def test_bedrock_rejects_unsupported_image_format() -> None:
    problem = ProblemInput(image=b"x", image_mime_type="image/heic")
    with pytest.raises(LLMError, match="heic"):
        _bedrock(FakeBedrock(), tool=False).generate(problem)


# --- Serveur auto-hébergé (API compatible OpenAI) ------------------------------------------


def _selfhosted(handler, api_key: str | None = "cle-locale") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="http://vllm.local:8000/v1/",
        model="Qwen/Qwen3-VL-8B-Instruct",
        system_prompt="prompt système",
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


def _completion(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 300},
        },
    )


def test_selfhosted_request_follows_openai_format() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _completion(SOLUTION_JSON)

    result = _selfhosted(handler).generate(PROBLEM)
    assert result.solution == make_solution()
    assert (result.stats.input_tokens, result.stats.output_tokens) == (900, 300)
    [request] = requests
    assert str(request.url) == "http://vllm.local:8000/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer cle-locale"
    body = json.loads(request.content)
    assert body["model"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert body["response_format"]["json_schema"]["schema"] == solution_json_schema()
    system, user = body["messages"]
    assert system == {"role": "system", "content": "prompt système"}
    image, text = user["content"]
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert text["type"] == "text" and "naka?" in text["text"]


def test_selfhosted_key_is_optional_and_repair_works() -> None:
    replies = iter([_completion("pas du json"), _completion(SOLUTION_JSON)])
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return next(replies)

    result = _selfhosted(handler, api_key=None).generate(PROBLEM)
    assert result.stats.attempts == 2
    assert "Authorization" not in seen[0].headers
    assert json.loads(seen[1].content)["messages"][-2]["role"] == "assistant"


def test_selfhosted_errors() -> None:
    with pytest.raises(LLMError, match="erreur 500"):
        _selfhosted(lambda r: httpx.Response(500, text="prompt: secret")).generate(PROBLEM)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé")

    with pytest.raises(LLMError, match="injoignable"):
        _selfhosted(unreachable).generate(PROBLEM)


# --- Liste blanche et fabrique --------------------------------------------------------------


def test_allowlist_entries_are_complete_and_open_source() -> None:
    allowlist = load_allowlist()
    assert allowlist.models
    for model in allowlist.models:
        assert model.provider in {"bedrock", "selfhosted"}
        assert model.license == "Apache-2.0"
        assert model.license_url.startswith("https://") and model.source.startswith("https://")
        assert model.supports_vision and model.regions


def test_allowlist_refuses_unknown_model_and_wrong_region() -> None:
    allowlist = load_allowlist()
    with pytest.raises(LLMConfigurationError, match="absent de la liste blanche"):
        allowlist.require("bedrock", "mistral.pixtral-large-2502-v1:0")
    with pytest.raises(LLMConfigurationError, match="région eu-west-3"):
        allowlist.require("bedrock", "mistral.ministral-3-14b-instruct", region="eu-west-3")
    with pytest.raises(LLMConfigurationError, match="inconnu"):
        allowlist.require("openai", "x")
    entry = allowlist.require("bedrock", "mistral.ministral-3-14b-instruct", region="eu-west-1")
    assert not entry.supports_tool_use


def test_create_llm_from_settings() -> None:
    settings = Settings(
        llm_provider="bedrock",
        bedrock_model_id="mistral.ministral-3-14b-instruct",
        bedrock_region="eu-west-1",
    )
    llm = create_llm(
        settings, lexicon_terms=["hypoténuse"], max_explanation_chars=500, bedrock_client=object()
    )
    assert isinstance(llm, BedrockProvider)
    assert (llm.name, llm.model, llm.region) == (
        "bedrock",
        "mistral.ministral-3-14b-instruct",
        "eu-west-1",
    )

    selfhosted = Settings(
        llm_provider="selfhosted",
        selfhosted_base_url="http://vllm:8000/v1",
        selfhosted_model="Qwen/Qwen3-VL-8B-Instruct",
    )
    assert isinstance(
        create_llm(selfhosted, lexicon_terms=[], max_explanation_chars=500),
        OpenAICompatibleProvider,
    )


def test_build_llm_enforces_allowlist_unless_disabled() -> None:
    with pytest.raises(LLMConfigurationError):
        build_llm(
            "selfhosted",
            "un/modele-inconnu",
            lexicon_terms=[],
            max_explanation_chars=10,
            base_url="http://x",
        )
    llm = build_llm(
        "selfhosted",
        "un/modele-inconnu",
        lexicon_terms=[],
        max_explanation_chars=10,
        base_url="http://x",
        enforce_allowlist=False,
    )
    assert llm.model == "un/modele-inconnu"
