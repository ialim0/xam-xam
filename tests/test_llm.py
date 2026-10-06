import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from fakes import make_solution
from xamxam.llm import LLMError, MathSolution, ProblemInput
from xamxam.llm.gemini import GeminiProvider
from xamxam.llm.prompts import build_system_prompt, build_user_prompt
from xamxam.llm.schema import solution_json_schema


class FakeModels:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(text=self.reply)


def _provider(reply: str | Exception) -> tuple[GeminiProvider, FakeModels]:
    models = FakeModels(reply)
    provider = GeminiProvider(
        api_key="cle",
        model="modele-de-test",
        lexicon_terms=["hypoténuse", "triangle rectangle"],
        max_explanation_chars=1000,
        client=SimpleNamespace(models=models),
    )
    return provider, models


def test_solution_uses_french_field_names() -> None:
    solution = make_solution()
    dumped = json.loads(solution.model_dump_json(by_alias=True))
    assert set(dumped) == {
        "statut", "enonce", "notion", "etapes", "reponse_finale",
        "termes_cles", "explication_wo", "calcul",
    }  # fmt: skip
    assert MathSolution.model_validate(dumped) == solution
    with pytest.raises(ValidationError):
        MathSolution.model_validate({**dumped, "notion": "algèbre"})


def test_json_schema_is_self_contained() -> None:
    schema = solution_json_schema()
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    assert {"enonce", "explication_wo", "calcul"} <= set(schema["properties"])
    assert "resultat" in schema["properties"]["calcul"]["properties"]


def test_system_prompt_contains_the_rules() -> None:
    prompt = build_system_prompt(["triangle rectangle", "hypoténuse"], 800)
    assert "hypoténuse, triangle rectangle" in prompt
    assert "800 caractères au maximum" in prompt
    assert "Commence toujours par rappeler les données lues" in prompt
    assert "image_illisible" in prompt and "hors_sujet" in prompt


def test_correction_prompt_includes_previous_answer_and_hint() -> None:
    previous = make_solution(resultat="7,5")
    problem = ProblemInput(text="?", previous=previous, correction="Le résultat correct est 7,21.")
    prompt = build_user_prompt(problem)
    assert "Le résultat correct est 7,21." in prompt
    assert '"resultat":"7,5"' in prompt


def test_gemini_sends_image_and_transcript() -> None:
    from google.genai import types

    provider, models = _provider(make_solution().model_dump_json(by_alias=True))
    problem = ProblemInput(image=b"\xff\xd8", image_mime_type="image/jpeg", transcript="naka?")
    assert provider.solve(problem) == make_solution()

    [call] = models.calls
    assert call["model"] == "modele-de-test"
    image, text = call["contents"]
    assert isinstance(image, types.Part) and image.inline_data.mime_type == "image/jpeg"
    assert "naka?" in text
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == solution_json_schema()
    assert "hypoténuse" in config.system_instruction


def test_gemini_rejects_invalid_output() -> None:
    provider, _ = _provider('{"statut": "ok"}')
    with pytest.raises(LLMError, match="non conforme"):
        provider.solve(ProblemInput(text="?"))


def test_gemini_errors_do_not_leak_content() -> None:
    provider, _ = _provider(RuntimeError("requête : numéro 221771234567"))
    with pytest.raises(LLMError) as raised:
        provider.solve(ProblemInput(text="?"))
    assert "221771234567" not in str(raised.value)
    assert "RuntimeError" in str(raised.value)


def test_gemini_requires_configuration_and_input() -> None:
    with pytest.raises(LLMError, match="GEMINI_MODEL"):
        GeminiProvider(api_key="cle", model="", lexicon_terms=[], max_explanation_chars=10)
    provider, _ = _provider("{}")
    with pytest.raises(LLMError, match="Rien à analyser"):
        provider.solve(ProblemInput())
