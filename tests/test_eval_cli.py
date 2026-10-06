import csv
import wave
from pathlib import Path

import pytest

from conftest import LEXICON_PATH, SENTENCES_PATH
from xamxam.eval.cli import main
from xamxam.eval.dataset import DatasetError, load_sentences
from xamxam.eval.metrics import Source
from xamxam.eval.records import OutputPaths, Version
from xamxam.eval.report import build_report
from xamxam.eval.run import run_evaluation
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


def test_run_and_report_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    common = ["--output-dir", str(out)]
    run_args = ["run", "--sentences", str(SENTENCES_PATH), "--lexicon", str(LEXICON_PATH), *common]

    assert main([*run_args, "--provider", "mock"]) == 0
    paths = OutputPaths(out)
    for sentence_id in ("P001", "P002", "P003", "T001", "C001"):
        for version in Version:
            with wave.open(str(paths.audio_file(sentence_id, version)), "rb") as wav:
                assert wav.getnframes() > 0

    human_rows = _read_csv(paths.human_csv)
    assert len(human_rows) == 10
    assert all(row["note_correction_wolof"] == "" for row in human_rows)

    # Une fiche déjà remplie n'est jamais écrasée par un nouveau `run`.
    paths.human_csv.write_text(paths.human_csv.read_text(encoding="utf-8") + "# annoté\n")
    assert main([*run_args, "--provider", "mock"]) == 0
    assert paths.human_csv.read_text(encoding="utf-8").endswith("# annoté\n")

    assert main(["report", *common]) == 0
    ranking = _read_csv(paths.ranking_csv)
    assert {row["terme"] for row in ranking} == {
        "triangle rectangle",
        "hypoténuse",
        "parallèle",
        "théorème de Pythagore",
    }
    assert "Taux d'erreur global" in paths.summary_md.read_text(encoding="utf-8")


def test_report_without_run_fails_cleanly(tmp_path: Path) -> None:
    assert main(["report", "--output-dir", str(tmp_path)]) == 1


def test_kvicc_provider_without_keys_fails_cleanly(tmp_path: Path) -> None:
    args = ["run", "--sentences", str(SENTENCES_PATH), "--lexicon", str(LEXICON_PATH)]
    assert main([*args, "--output-dir", str(tmp_path), "--provider", "kvicc"]) == 1


def test_improvement_is_measured(tmp_path: Path) -> None:
    # STT simulé qui déforme « hypoténuse » prononcé à l'anglaise mais comprend la réécriture.
    def stt_transform(text: str) -> str:
        return text.replace("Hypoténuse", "haïpoteniouz")

    paths = OutputPaths(tmp_path)
    run_evaluation(
        load_sentences(SENTENCES_PATH),
        pipeline=XamXamPipeline.from_lexicon_file(LEXICON_PATH),
        tts=MockTTSProvider(),
        stt=MockSTTProvider(stt_transform),
        paths=paths,
    )
    report = build_report(paths)
    [hyp] = [s for s in report.ranking if s.term == "hypoténuse"]
    assert hyp.rate(Source.STT, Version.BEFORE) == 1.0
    assert hyp.rate(Source.STT, Version.AFTER) == 0.0
    assert "100,0 %" in paths.summary_md.read_text(encoding="utf-8")
