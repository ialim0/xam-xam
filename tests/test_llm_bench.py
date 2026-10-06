import csv
from pathlib import Path

import pytest

from fakes import make_solution
from xamxam.eval.llm_bench import (
    BenchmarkError,
    ConfiguredModel,
    ImageType,
    ModelConfig,
    load_configs,
    load_ground_truth,
    parse_values,
    run_llm_benchmark,
    summarize,
    write_outputs,
)
from xamxam.llm import CallStats, LLMError
from xamxam.llm.mock import ScriptedLLM

GROUND_TRUTH = """fichier,type_image,notion,type_calcul,donnees,resultat_attendu
ex1.jpg,imprime,pythagore,pythagore_hypotenuse,cote1=4;cote2=6,√52
ex2.png,manuscrit,thales,thales_longueur,a=2;b=6;c=1.5,"4,5"
"""


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    (tmp_path / "ex1.jpg").write_bytes(b"\xff\xd8 imprime")
    (tmp_path / "ex2.png").write_bytes(b"\x89PNG manuscrit")
    (tmp_path / "verite_terrain.csv").write_text(GROUND_TRUTH, encoding="utf-8")
    return tmp_path


THALES_OK = make_solution(
    notion="thales",
    calcul={
        "type": "thales_longueur",
        "donnees": [
            {"nom": "a", "valeur": 2},
            {"nom": "b", "valeur": 6},
            {"nom": "c", "valeur": 1.5},
        ],
        "resultat": "4,5",
    },
)


def test_load_inputs(photos: Path, tmp_path: Path) -> None:
    cases = load_ground_truth(photos / "verite_terrain.csv")
    assert [c.image_type for c in cases] == [ImageType.PRINTED, ImageType.HANDWRITTEN]
    assert cases[1].values == {"a": 2.0, "b": 6.0, "c": 1.5}
    assert parse_values("x = 3,5 ; y=2") == {"x": 3.5, "y": 2.0}

    configs = tmp_path / "configs.json"
    configs.write_text(
        '[{"nom": "a", "provider": "selfhosted", "modele": "m", "prix_entree_par_million": 0.1,'
        ' "prix_sortie_par_million": 0.3}]',
        encoding="utf-8",
    )
    [config] = load_configs(configs)
    assert config.cost(1_000_000, 1_000_000) == pytest.approx(0.4)
    assert ModelConfig("b", "bedrock", "m").cost(10, 10) is None


@pytest.mark.parametrize(
    "row",
    ["ex.jpg,photo,pythagore,pythagore_hypotenuse,cote1=4,5", "ex.jpg,imprime,x,inconnu,a=1,1"],
)
def test_invalid_ground_truth(tmp_path: Path, row: str) -> None:
    path = tmp_path / "v.csv"
    path.write_text(
        "fichier,type_image,notion,type_calcul,donnees,resultat_attendu\n" + row, encoding="utf-8"
    )
    with pytest.raises(BenchmarkError, match="ligne 2"):
        load_ground_truth(path)


def test_benchmark_metrics_and_outputs(photos: Path, tmp_path: Path) -> None:
    cases = load_ground_truth(photos / "verite_terrain.csv")
    good = ScriptedLLM(
        [make_solution(), make_solution(), THALES_OK, THALES_OK],
        stats=CallStats(latency_ms=800, input_tokens=1000, output_tokens=500),
    )
    # Second modèle : mauvais résultat une fois, extraction fausse, puis échec JSON.
    wrong_data = make_solution(
        calcul={
            "type": "pythagore_hypotenuse",
            "donnees": [{"nom": "cote1", "valeur": 4}, {"nom": "cote2", "valeur": 5}],
            "resultat": "√41",
        }
    )
    weak = ScriptedLLM(
        [make_solution(resultat="7,5"), wrong_data, THALES_OK, LLMError("JSON")],
        stats=CallStats(latency_ms=200, input_tokens=100, output_tokens=50, attempts=2),
    )
    models = [
        ConfiguredModel(
            ModelConfig(
                "fort",
                "selfhosted",
                "m1",
                price_input_per_million=1.0,
                price_output_per_million=2.0,
            ),
            good,
        ),
        ConfiguredModel(ModelConfig("faible", "selfhosted", "m2"), weak),
    ]
    records = run_llm_benchmark(cases, photos, models, repetitions=2)
    assert len(records) == 8
    assert good.calls[0].image_mime_type == "image/jpeg"
    assert good.calls[2].image_mime_type == "image/png"

    strong, weak_summary = summarize(records)
    assert strong.name == "fort"
    assert (strong.json_first_try, strong.extraction_ok, strong.result_ok) == (4, 4, 4)
    assert strong.stability == 1.0 and strong.latency_median_ms == 800
    assert strong.mean_cost == pytest.approx(0.002)
    assert strong.result_by_image_type[ImageType.HANDWRITTEN] == (2, 2)

    assert (weak_summary.json_valid, weak_summary.json_first_try) == (3, 0)
    assert (weak_summary.extraction_ok, weak_summary.result_ok) == (2, 1)
    assert weak_summary.stability == pytest.approx(0.5)  # 7,50 puis 6,40 ; 4,50 puis échec
    assert weak_summary.mean_cost is None

    out = tmp_path / "sortie"
    write_outputs(records, out, repetitions=2)
    with (out / "resultats.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 8 and rows[-1]["erreur"] == "LLMError"
    with (out / "notation_wolof.csv").open(encoding="utf-8") as file:
        rating = list(csv.DictReader(file))
    assert len(rating) == 7 and rating[0]["note_wolof"] == ""
    report = (out / "rapport.md").read_text(encoding="utf-8")
    assert "| fort | 4 | 100 % |" in report and "Manuscrit" in report

    # La fiche de notation déjà remplie n'est jamais écrasée.
    (out / "notation_wolof.csv").write_text("annoté", encoding="utf-8")
    write_outputs(records, out, repetitions=2)
    assert (out / "notation_wolof.csv").read_text(encoding="utf-8") == "annoté"


def test_cli_llm_with_unknown_model_fails_cleanly(photos: Path, tmp_path: Path) -> None:
    from xamxam.eval.cli import main

    configs = tmp_path / "c.json"
    configs.write_text(
        '[{"nom": "x", "provider": "selfhosted", "modele": "inconnu/x", "base_url": "http://x"}]',
        encoding="utf-8",
    )
    assert (
        main(
            [
                "llm",
                "--photos",
                str(photos),
                "--configs",
                str(configs),
                "--output-dir",
                str(tmp_path / "o"),
            ]
        )
        == 1
    )
