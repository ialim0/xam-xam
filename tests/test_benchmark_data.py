"""Contrôles du jeu de 100 phrases et du lexique réels du dépôt (python -m xamxam.eval check)."""

import csv
import json
from pathlib import Path

import pytest

from conftest import REPO_LEXICON_PATH, REPO_SENTENCES_PATH
from xamxam.eval.check import CheckLimits, check_sentences, count_words, is_rich
from xamxam.eval.dataset import Sentence, load_sentences
from xamxam.lexicon import VALIDATED_AND_DRAFT, Lexicon, LexiconIndex, TermStatus
from xamxam.lexicon.validation import VALIDATION_COLUMNS, read_validation_csv
from xamxam.pipeline import XamXamPipeline

VALIDATION_PATH = REPO_LEXICON_PATH.parent / "termes_cibles_a_valider.csv"


@pytest.fixture
def repo_pipeline(repo_lexicon: Lexicon) -> XamXamPipeline:
    # Pire cas pour la longueur : toutes les prononciations appliquées.
    return XamXamPipeline(repo_lexicon, applied_statuses=VALIDATED_AND_DRAFT)


def test_benchmark_dataset_passes_all_checks(repo_pipeline: XamXamPipeline) -> None:
    report = check_sentences(load_sentences(REPO_SENTENCES_PATH), repo_pipeline)
    assert report.errors == []
    assert len(report.sentences) == 100
    assert len(report.terms) >= 28  # « environ 30 termes cibles »
    assert all(stats.occurrences >= 4 for stats in report.terms.values())
    assert sum(r.rich for r in report.sentences) >= 60
    # Après Xam-Xam, plus aucun caractère n'est perdu par le TTS.
    assert all(r.lost_normalized == [] for r in report.sentences)


def test_wolof_column_is_marked_as_draft() -> None:
    with REPO_SENTENCES_PATH.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert {row["statut_wo"] for row in rows} == {"brouillon"}


def test_repo_lexicon_covers_targets_with_explicit_status(repo_lexicon: Lexicon) -> None:
    raw = json.loads(REPO_LEXICON_PATH.read_text(encoding="utf-8"))
    assert all("statut" in entry for entry in raw["terms"])
    index = LexiconIndex(repo_lexicon)
    targets = {t for s in load_sentences(REPO_SENTENCES_PATH) for t in s.target_terms}
    assert [t for t in targets if index.lookup(t) is None] == []
    # Aucune prononciation n'est encore validée par un locuteur natif.
    assert {t.status for t in repo_lexicon.terms} == {TermStatus.DRAFT}


def test_validation_file_matches_dataset() -> None:
    rows = read_validation_csv(VALIDATION_PATH)
    targets = {t for s in load_sentences(REPO_SENTENCES_PATH) for t in s.target_terms}
    assert {row["terme"] for row in rows} == targets
    assert all(int(row["nombre_occurrences"]) >= 4 for row in rows)
    assert all(row["prononciation_validee"] == "" and row["validateur"] == "" for row in rows)
    assert all("BROUILLON" in row["remarques"] for row in rows)
    with VALIDATION_PATH.open(encoding="utf-8") as file:
        assert tuple(next(csv.reader(file))) == VALIDATION_COLUMNS


def test_word_count_and_rich_detection() -> None:
    assert count_words("AM/AB = AN/AC : rapport yi yem nañu.") == 6
    assert count_words("(MN) // (BC)") == 2
    assert is_rich("BC = 5 cm") and is_rich("3,6") and is_rich("12 mètres") and is_rich("√52")
    assert not is_rich("Ci benn triangle rectangle, 3 côté yi.")


def _sentence(id_: str, wo: str, terms: str, notion: str = "pythagore") -> Sentence:
    return Sentence(id_, notion, "test", "fr", wo, tuple(t for t in terms.split(";") if t))


def test_check_reports_each_kind_of_error(pipeline: XamXamPipeline) -> None:
    sentences = [
        _sentence("P001", "Hypoténuse bi am na 25 cm.", "hypoténuse"),
        _sentence("P002", "Ci kaw " + "mot " * 25, ""),
        _sentence("P002", "Ci triangle bi, BC = 3 cm.", "angle droit"),
        _sentence("T001", "x " * 300 + "AB²", "", notion="pythagore"),
    ]
    report = check_sentences(
        sentences,
        pipeline,
        CheckLimits(expected_rows=100, min_occurrences=2, max_chars=512, min_rich_sentences=10),
    )
    text = "\n".join(report.errors)
    assert "4 lignes au lieu de 100" in text
    assert "identifiants P" in text and "notion différente de « thales » : T001" in text
    assert "P002 : 27 mots" in text
    assert "P002 : terme cible « angle droit » absent" in text
    assert "T001 :" in text and "caractères après normalisation" in text
    assert "terme « hypoténuse » : 1 occurrence(s) (minimum 2)" in text
    assert "phrases avec nombres > 10" in text
    assert not report.ok


def test_cli_check_on_repo_data() -> None:
    from xamxam.eval.cli import main

    assert (
        main(
            ["check", "--sentences", str(REPO_SENTENCES_PATH), "--lexicon", str(REPO_LEXICON_PATH)]
        )
        == 0
    )


def test_cli_check_fails_on_bad_dataset(tmp_path: Path) -> None:
    from xamxam.eval.cli import main

    bad = tmp_path / "phrases.csv"
    bad.write_text(
        "id,notion,contexte,fr,wo,termes_cibles\nP001,pythagore,c,fr,wo,hypoténuse\n",
        encoding="utf-8",
    )
    assert main(["check", "--sentences", str(bad), "--lexicon", str(REPO_LEXICON_PATH)]) == 1
