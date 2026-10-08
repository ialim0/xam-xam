import csv
import wave
from pathlib import Path

import pytest

from conftest import LEXICON_PATH, SENTENCES_PATH
from xamxam.eval.cli import main
from xamxam.eval.dataset import DatasetError, load_sentences
from xamxam.eval.metrics import LAYERS, Source
from xamxam.eval.records import Condition, OutputPaths
from xamxam.eval.report import build_report
from xamxam.eval.run import build_target, run_evaluation
from xamxam.lexicon import VALIDATED_AND_DRAFT, VALIDATED_ONLY, LexiconIndex
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockSTTProvider, MockTTSProvider


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_example_dataset_is_valid() -> None:
    sentences = load_sentences(SENTENCES_PATH)
    assert len(sentences) == 5
    assert {s.notion for s in sentences} == {"pythagore", "thales", "concret"}
    assert all(s.target_terms for s in sentences)


def test_draft_pronunciation_is_not_counted_as_validated(pipeline: XamXamPipeline) -> None:
    index = LexiconIndex(pipeline.index.lexicon)
    validated = build_target("hypoténuse", index, VALIDATED_ONLY)
    experimental = build_target("hypoténuse", index, VALIDATED_AND_DRAFT)
    assert "ipoteniws" not in validated.accepted_forms
    assert "ipoteniws" in experimental.accepted_forms


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("P1,geometrie,c,fr,wo,t", "notion"),
        ("P 1,pythagore,c,fr,wo,t", "identifiant invalide"),
        ("P1,pythagore,c,,,t", "vides"),
    ],
)
def test_invalid_dataset_rows(tmp_path: Path, row: str, message: str) -> None:
    path = tmp_path / "phrases.csv"
    path.write_text(f"id,notion,contexte,fr,wo,termes_cibles\n{row}\n", encoding="utf-8")
    with pytest.raises(DatasetError, match=message):
        load_sentences(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "phrases.csv"
    row = "P1,pythagore,c,fr,wo,t"
    path.write_text(f"id,notion,contexte,fr,wo,termes_cibles\n{row}\n{row}\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="double"):
        load_sentences(path)


def test_run_and_report_end_to_end(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    out = tmp_path / "outputs"
    common = ["--output-dir", str(out)]
    run_args = [
        "run",
        "--sentences",
        str(SENTENCES_PATH),
        "--lexicon",
        str(LEXICON_PATH),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--provider",
        "mock",
        *common,
    ]

    with caplog.at_level("INFO"):
        assert main(run_args) == 0
    # 15 audios demandés, mais une phrase sans maths donne le même texte brut et normalisé.
    assert "Cache audio" in caplog.text
    paths = OutputPaths(out)
    for sentence_id in ("P001", "P002", "P003", "T001", "C001"):
        for condition in Condition:
            with wave.open(str(paths.audio_file(sentence_id, condition)), "rb") as wav:
                assert wav.getnframes() > 0

    human_rows = _read_csv(paths.human_csv)
    assert len(human_rows) == 15
    assert {row["condition"] for row in human_rows} == {"brut", "normalise", "lexique"}
    assert all(row["note_correction_wolof"] == "" for row in human_rows)

    # Une fiche déjà remplie n'est jamais écrasée par un nouveau `run`.
    paths.human_csv.write_text(paths.human_csv.read_text(encoding="utf-8") + "# annoté\n")
    caplog.clear()
    with caplog.at_level("INFO"):
        assert main(run_args) == 0
    # Deuxième passage : tous les audios viennent du cache.
    assert "0 généré(s)" in caplog.text
    assert paths.human_csv.read_text(encoding="utf-8").endswith("# annoté\n")

    assert main(["report", *common]) == 0
    ranking = _read_csv(paths.ranking_csv)
    assert {row["terme"] for row in ranking} == {
        "triangle rectangle",
        "hypoténuse",
        "parallèle",
        "théorème de Pythagore",
    }
    assert "taux_normalise_combine" in ranking[0]
    summary = paths.summary_md.read_text(encoding="utf-8")
    assert "Apport de chaque couche" in summary
    assert "Normalisé + lexique" in summary


def test_report_without_run_fails_cleanly(tmp_path: Path) -> None:
    assert main(["report", "--output-dir", str(tmp_path)]) == 1


def test_audio_only_creates_blind_sheet_without_stt(tmp_path: Path) -> None:
    paths = OutputPaths(tmp_path / "outputs")
    args = ["--output-dir", str(paths.root)]
    assert (
        main(
            [
                "audio",
                "--sentences",
                str(SENTENCES_PATH),
                "--lexicon",
                str(LEXICON_PATH),
                "--provider",
                "mock",
                "--cache-dir",
                str(tmp_path / "cache"),
                "--lexique-statut",
                "brouillon",
                *args,
            ]
        )
        == 0
    )
    assert len(_read_csv(paths.audio_manifest_csv)) == 15
    assert not paths.transcriptions_csv.exists()
    assert len(_read_csv(paths.human_csv)) == 15
    assert main(["blind", *args]) == 0
    blind_rows = _read_csv(paths.blind_csv)
    assert len(blind_rows) == 15
    blind_rows[0]["note_correction_wolof"] = "4"
    with paths.blind_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=blind_rows[0].keys())
        writer.writeheader()
        writer.writerows(blind_rows)
    assert main(["unblind", *args]) == 0
    assert main(["report", *args]) == 1  # le rapport exige toujours les résultats STT
    assert (
        main(
            [
                "run",
                "--sentences",
                str(SENTENCES_PATH),
                "--lexicon",
                str(LEXICON_PATH),
                "--provider",
                "mock",
                "--lexique-statut",
                "brouillon",
                "--cache-dir",
                str(tmp_path / "cache"),
                *args,
            ]
        )
        == 0
    )
    assert main(["report", *args]) == 0
    assert "Lignes annotées par des évaluateurs humains : 1" in paths.summary_md.read_text(
        encoding="utf-8"
    )


def test_blind_human_rating_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    args = ["--output-dir", str(out)]
    assert (
        main(
            [
                "run",
                "--sentences",
                str(SENTENCES_PATH),
                "--lexicon",
                str(LEXICON_PATH),
                "--provider",
                "mock",
                "--no-cache",
                *args,
            ]
        )
        == 0
    )
    assert main(["blind", "--seed", "7", *args]) == 0
    paths = OutputPaths(out)
    rows = _read_csv(paths.blind_csv)
    assert len(rows) == 15
    assert "condition" not in rows[0] and "texte_envoye" not in rows[0]
    assert len({row["fichier_audio"] for row in rows}) == 15
    assert all((paths.blind_dir / row["fichier_audio"]).is_file() for row in rows)
    assert main(["blind", *args]) == 1  # ne jamais effacer des notes par inadvertance

    rows[0]["note_correction_wolof"] = "4"
    rows[0]["note_prononciation_termes"] = "5"
    with paths.blind_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    sample_audio = paths.blind_dir / rows[0]["fichier_audio"]
    original_audio = sample_audio.read_bytes()
    sample_audio.write_bytes(b"modified audio")
    assert main(["unblind", *args]) == 1
    sample_audio.write_bytes(original_audio)
    assert main(["unblind", *args]) == 0
    assert main(["report", *args]) == 0
    assert len(_read_csv(paths.human_csv)) == 15
    assert "Lignes annotées par des évaluateurs humains : 1" in paths.summary_md.read_text(
        encoding="utf-8"
    )
    assert main(["unblind", *args]) == 1  # protège les notes déjà importées


def test_kvicc_provider_without_keys_fails_cleanly(tmp_path: Path) -> None:
    args = ["run", "--sentences", str(SENTENCES_PATH), "--lexicon", str(LEXICON_PATH)]
    assert main([*args, "--output-dir", str(tmp_path), "--provider", "kvicc"]) == 1


def test_each_layer_contribution_is_measured(tmp_path: Path) -> None:
    # STT simulé : « hypoténuse » non réécrit est déformé, seul le lexique corrige.
    def stt_transform(text: str) -> str:
        return text.replace("Hypoténuse", "haïpoteniouz")

    paths = OutputPaths(tmp_path)
    run_evaluation(
        load_sentences(SENTENCES_PATH),
        pipeline=XamXamPipeline.from_lexicon_file(
            LEXICON_PATH, applied_statuses=VALIDATED_AND_DRAFT
        ),
        tts=MockTTSProvider(),
        stt=MockSTTProvider(stt_transform),
        paths=paths,
    )
    report = build_report(paths)
    normalization, lexicon = LAYERS
    [hyp] = [s for s in report.ranking if s.term == "hypoténuse"]
    assert [hyp.rate(Source.STT, c) for c in Condition] == [1.0, 1.0, 0.0]
    assert (hyp.layer_gain(normalization), hyp.layer_gain(lexicon)) == (0.0, 1.0)
    assert "+100,0 pts" in paths.summary_md.read_text(encoding="utf-8")


def test_lexicon_status_limit_and_report_parameters(tmp_path: Path) -> None:
    import json

    common = ["--output-dir", str(tmp_path), "--provider", "mock", "--no-cache"]
    data = ["--sentences", str(SENTENCES_PATH), "--lexicon", str(LEXICON_PATH)]

    # Par défaut : prononciations validées seulement (aucune dans le lexique de test).
    assert main(["run", *data, *common, "--limit", "2"]) == 0
    info = json.loads((tmp_path / "run_info.json").read_text(encoding="utf-8"))
    assert info["phrases"] == 2 and info["langue_nombres"] == "fr"
    assert info["lexique_statut"] == "valide"
    assert info["termes_appliques"]["valide"]["occurrences"] == 0
    assert info["termes_appliques"]["brouillon"]["occurrences"] == 0
    assert len(_read_csv(OutputPaths(tmp_path).transcriptions_csv)) == 6  # 2 phrases × 3

    assert main(["run", *data, *common, "--lexique-statut", "brouillon", "--overwrite-human"]) == 0
    info = json.loads((tmp_path / "run_info.json").read_text(encoding="utf-8"))
    assert info["lexique_statut"] == "brouillon"
    assert info["termes_appliques"]["brouillon"]["occurrences"] > 0
    assert "triangle rectangle" in info["termes_appliques"]["brouillon"]["termes"]

    assert main(["report", "--output-dir", str(tmp_path)]) == 0
    summary = OutputPaths(tmp_path).summary_md.read_text(encoding="utf-8")
    assert "Langue des nombres : **français** (`--number-language fr`)" in summary
    assert "prononciations validées et brouillons" in summary
    assert "prononciation **validée** : 0 occurrence" in summary
    assert "Des prononciations brouillon ont été appliquées" in summary


def test_invalid_limit_fails_cleanly(tmp_path: Path) -> None:
    args = ["run", "--sentences", str(SENTENCES_PATH), "--lexicon", str(LEXICON_PATH)]
    assert main([*args, "--output-dir", str(tmp_path), "--provider", "mock", "--limit", "0"]) == 1
