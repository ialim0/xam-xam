import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from fakes import make_solution
from xamxam.config import Settings
from xamxam.llm import LLMConfigurationError, LLMError, MathSolution, ProblemInput
from xamxam.llm.factory import create_llm
from xamxam.llm.gemini import GeminiHTTP, GeminiProvider
from xamxam.llm.prompts import build_system_prompt, build_user_prompt
from xamxam.llm.schema import solution_json_schema
from xamxam.llm.structured import (
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


# --- Gemini (generateContent) --------------------------------------------------------------


def _gemini(handler, **kwargs) -> GeminiProvider:
    return GeminiProvider(
        api_key="g-secret",
        model="gemini-3.5-flash",
        system_prompt="prompt système",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        **kwargs,
    )


def _candidate(text: str, *, thought: str | None = None) -> httpx.Response:
    parts: list[dict[str, Any]] = [{"text": thought, "thought": True}] if thought else []
    parts.append({"text": text})
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": parts}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 300},
        },
    )


def _model_of(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1].split(":")[0]


def test_gemini_sends_image_inline_and_requests_json() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _candidate(SOLUTION_JSON, thought="je réfléchis")

    result = _gemini(handler).generate(PROBLEM)
    assert result.solution == make_solution()
    assert (result.stats.input_tokens, result.stats.output_tokens) == (900, 300)
    [request] = requests
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
    )
    assert request.headers["x-goog-api-key"] == "g-secret"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "prompt système"}]}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    [content] = body["contents"]
    image, text = content["parts"]
    assert image == {"inline_data": {"mime_type": "image/jpeg", "data": "/9hwaG90bw=="}}
    assert "naka?" in text["text"]


def test_gemini_repairs_invalid_json_once() -> None:
    replies = iter([_candidate("pas du json"), _candidate(SOLUTION_JSON)])
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return next(replies)

    result = _gemini(handler).generate(PROBLEM)
    assert result.solution == make_solution() and result.stats.attempts == 2
    roles = [c["role"] for c in json.loads(seen[1].content)["contents"]]
    assert roles == ["user", "model", "user"]

    with pytest.raises(InvalidStructuredOutputError, match="après réparation"):
        _gemini(lambda r: _candidate("toujours pas")).generate(PROBLEM)


def test_gemini_errors_do_not_leak_content_or_key() -> None:
    with pytest.raises(LLMError, match="erreur 400") as raised:
        _gemini(lambda r: httpx.Response(400, text="prompt: secret")).generate(PROBLEM)
    assert "secret" not in str(raised.value)
    with pytest.raises(LLMError, match="aucun candidat"):
        _gemini(lambda r: httpx.Response(200, json={"candidates": []})).generate(PROBLEM)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé")

    with pytest.raises(LLMError, match="injoignable"):
        _gemini(unreachable).generate(PROBLEM)
    with pytest.raises(LLMError, match="Format d'image"):
        _gemini(_candidate).generate(ProblemInput(image=b"x", image_mime_type="image/gif"))
    assert "g-secret" not in repr(_gemini(_candidate))


def test_create_llm_from_settings() -> None:
    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        create_llm(Settings(), lexicon_terms=[], max_explanation_chars=500)
    llm = create_llm(
        Settings(gemini_api_key="g", gemini_model="gemini-3.8-flash"),
        lexicon_terms=["hypoténuse"],
        max_explanation_chars=500,
    )
    assert isinstance(llm, GeminiProvider)
    assert (llm.name, llm.model) == ("gemini", "gemini-3.8-flash")


def test_gemini_retries_then_falls_back_to_the_next_model() -> None:
    seen: list[str] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_model_of(request))
        if _model_of(request) == "gemini-3.5-flash":
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        return _candidate(SOLUTION_JSON)

    provider = GeminiProvider(
        api_key="g",
        model="gemini-3.5-flash",
        fallback_models=["gemini-3.6-flash"],
        system_prompt="s",
        transport=httpx.MockTransport(handler),
        sleep=waits.append,
    )
    assert provider.generate(PROBLEM).solution == make_solution()
    assert seen == ["gemini-3.5-flash", "gemini-3.5-flash", "gemini-3.6-flash"]
    assert waits == [1.0]

    # Une erreur définitive (clé invalide…) n'est ni réessayée ni contournée.
    seen.clear()
    provider = _gemini(
        lambda r: (seen.append("x"), httpx.Response(400))[1],
        fallback_models=["gemini-3.6-flash"],
    )
    with pytest.raises(LLMError, match="erreur 400"):
        provider.generate(PROBLEM)
    assert seen == ["x"]


def test_gemini_timeout_moves_to_the_fallback_model() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_model_of(request))
        if _model_of(request) == "gemini-3.5-flash":
            raise httpx.ReadTimeout("saturé")
        return _candidate(SOLUTION_JSON)

    provider = _gemini(handler, fallback_models=["gemini-3.6-flash"])
    assert provider.generate(PROBLEM).solution == make_solution()
    assert seen == ["gemini-3.5-flash", "gemini-3.6-flash"]


def test_saturated_model_is_skipped_during_cooldown() -> None:
    seen: list[str] = []
    now = [0.0]
    primary_down = [True]

    def handler(request: httpx.Request) -> httpx.Response:
        model = _model_of(request)
        seen.append(model)
        if model == "principal" and primary_down[0]:
            return httpx.Response(503)
        return _candidate(SOLUTION_JSON)

    gemini = GeminiHTTP(
        api_key="g",
        models=["principal", "repli"],
        transport=httpx.MockTransport(handler),
        attempts_per_model=1,
        cooldown_seconds=60,
        clock=lambda: now[0],
    )
    gemini.post({"contents": []})
    gemini.post({"contents": []})  # le principal est écarté : pas d'attente inutile
    assert seen == ["principal", "repli", "repli"]

    now[0], primary_down[0] = 61, False  # fin de la pause : on retente le principal
    gemini.post({"contents": []})
    assert seen[-1] == "principal"
