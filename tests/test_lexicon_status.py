import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from xamxam.lexicon import (
    VALIDATED_AND_DRAFT,
    Lexicon,
    LexiconError,
    LexiconIndex,
    Term,
    TermStatus,
    load_lexicon,
)
from xamxam.lexicon.__main__ import main as lexicon_cli
from xamxam.lexicon.convert import convert_entry, convert_source, lexicon_to_json
from xamxam.lexicon.validation import apply_validations, write_validation_csv
from xamxam.pipeline import XamXamPipeline

LEXICON = Lexicon.model_validate(
    {
        "version": "t",
        "language": "wo",
        "terms": [
            {
                "term": "hypoténuse",
                "pronunciation": "ipoteniws",
                "statut": "valide",
                "validated_by": "Awa",
            },
            {"term": "triangle rectangle", "pronunciation": "tiriyaangal regtaangal"},
            {
                "term": "triangle",
                "pronunciation": "tiriyaangal",
                "statut": "valide",
                "validated_by": "Awa",
            },
            {"term": "somme"},
        ],
    }
)
TEXT = "Ci triangle rectangle, hypoténuse ak somme ; triangle bi."


# --- Statuts et couche de prononciation ------------------------------------------------------


def test_default_pipeline_applies_only_validated_terms() -> None:
    prepared = XamXamPipeline(LEXICON).prepare(TEXT)
    # « triangle rectangle » est brouillon : laissé intact en entier (pas de réécriture
    # partielle), alors que « triangle » seul, validé, est réécrit plus loin.
    assert prepared.text == "Ci triangle rectangle, ipoteniws ak somme; tiriyaangal bi."
    assert {r.status for r in prepared.replacements} == {TermStatus.VALIDATED}


def test_draft_mode_applies_drafts_but_never_terms_without_pronunciation() -> None:
    prepared = XamXamPipeline(LEXICON, applied_statuses=VALIDATED_AND_DRAFT).prepare(TEXT)
    assert prepared.text == "Ci tiriyaangal regtaangal, ipoteniws ak somme; tiriyaangal bi."
    assert [r.status for r in prepared.replacements] == [
        TermStatus.DRAFT,
        TermStatus.VALIDATED,
        TermStatus.VALIDATED,
    ]


def test_full_index_still_knows_every_term() -> None:
    pipeline = XamXamPipeline(LEXICON)
    assert pipeline.index.lookup("somme") is not None
    assert pipeline.index.lookup("triangle rectangle").status is TermStatus.DRAFT


def test_validated_term_requires_pronunciation_and_validator() -> None:
    with pytest.raises(ValidationError, match="valide sans prononciation ou sans validateur"):
        Term.model_validate({"term": "somme", "statut": "valide", "validated_by": "Awa"})
    with pytest.raises(ValidationError, match="sans validateur"):
        Term.model_validate({"term": "somme", "pronunciation": "som", "statut": "valide"})
    assert Term.model_validate({"term": "somme"}).status is TermStatus.DRAFT


# --- Conversion du lexique source ----------------------------------------------------------

SOURCE = {
    "version": "v0-source",
    "termes": [
        {
            "id": "PYT-001",
            "terme_fr": "hypoténuse",
            "domaine": "géométrie",
            "sous_domaine": "triangle rectangle",
            "niveau_indicatif": "4e",
            "risque_lecture_anglaise": "élevé",
            "wolof": {
                "equivalent": "wet bu gën a gudd",
                "prononciation": "ipoteniws",
                "valide_par": "Awa Ndiaye",
                "statut": "validé",
                "commentaire": "accent sur la fin",
            },
            "phrases_test": ["Hypoténuse bi tollu na 5 cm."],
            "source_manuel": "CIAM 4e",
        },
        {
            "id": "PYT-002",
            "terme_fr": "racine carrée",
            "wolof": {"equivalent": "", "prononciation": "", "valide_par": "", "statut": "à faire"},
            "phrases_test": "√25 = 5",
        },
        {
            "id": "PYT-003",
            "terme_fr": "carré",
            "wolof": {"prononciation": "kaare", "valide_par": "", "statut": "validé"},
        },
    ],
}


def test_convert_entry_keeps_every_useful_field() -> None:
    entry = convert_entry(SOURCE["termes"][0])
    assert entry["term"] == "hypoténuse" and entry["pronunciation"] == "ipoteniws"
    assert entry["statut"] is TermStatus.VALIDATED and entry["validated_by"] == "Awa Ndiaye"
    assert entry["equivalent_wo"] == "wet bu gën a gudd"
    assert (entry["domaine"], entry["sous_domaine"], entry["niveau_indicatif"]) == (
        "géométrie",
        "triangle rectangle",
        "4e",
    )
    assert entry["risque_lecture_anglaise"] == "élevé"
    assert entry["phrases_test"] == ["Hypoténuse bi tollu na 5 cm."]
    # Champs non prévus par le schéma : conservés dans « autres ».
    assert entry["autres"] == {
        "wolof": {"commentaire": "accent sur la fin"},
        "source_manuel": "CIAM 4e",
    }


def test_convert_source_statuses_and_missing_pronunciations() -> None:
    lexicon = convert_source(SOURCE)
    hyp, root, square = lexicon.terms
    assert lexicon.version == "v0-source"
    assert hyp.status is TermStatus.VALIDATED and hyp.source_id == "PYT-001"
    # Sans prononciation : présent, brouillon, jamais appliqué.
    assert root.pronunciation is None and root.status is TermStatus.DRAFT
    assert root.test_sentences == ("√25 = 5",) and root.extra == {"statut_source": "à faire"}
    # « validé » sans validateur : rétrogradé en brouillon, statut d'origine conservé.
    assert square.status is TermStatus.DRAFT and square.extra == {"statut_source": "validé"}
    prepared = XamXamPipeline(lexicon, applied_statuses=VALIDATED_AND_DRAFT).prepare(
        "racine carrée ak carré ak hypoténuse"
    )
    assert prepared.text == "racine carrée ak kaare ak ipoteniws"


def test_converted_json_round_trips(tmp_path: Path) -> None:
    lexicon = convert_source(SOURCE)
    text = lexicon_to_json(lexicon)
    data = json.loads(text)
    assert all(entry["statut"] in {"valide", "brouillon"} for entry in data["terms"])
    assert "pronunciation" not in data["terms"][1]  # champ vide omis
    path = tmp_path / "lexique.json"
    path.write_text(text, encoding="utf-8")
    assert load_lexicon(path) == lexicon


def test_convert_cli_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(SOURCE["termes"]), encoding="utf-8")  # liste à la racine
    destination = tmp_path / "lexique.json"
    assert lexicon_cli(["convert", str(source), str(destination)]) == 0
    assert "3 termes convertis" in capsys.readouterr().out
    duplicated = {"termes": [SOURCE["termes"][0], SOURCE["termes"][0]]}
    with pytest.raises(LexiconError, match="deux fois"):
        convert_source(duplicated)
    with pytest.raises(LexiconError, match="introuvable"):
        convert_source({"autre": []})


# --- Validation par des locuteurs natifs ---------------------------------------------------


def _rows(*rows: tuple[str, str, str]) -> list[dict[str, str]]:
    return [
        {"terme": t, "prononciation_validee": p, "validateur": v, "remarques": ""}
        for t, p, v in rows
    ]


def test_import_validations_updates_status() -> None:
    updated, summary = apply_validations(
        LEXICON,
        _rows(
            ("triangle rectangle", "tiriyaangal rektaangal", "Moussa"),
            ("somme", "som", "Moussa"),
            ("diagonale", "jaagonaal", "Moussa"),
            ("hypoténuse", "", ""),
        ),
    )
    index = LexiconIndex(updated)
    rect = index.lookup("triangle rectangle")
    assert (rect.status, rect.pronunciation, rect.validated_by) == (
        TermStatus.VALIDATED,
        "tiriyaangal rektaangal",
        "Moussa",
    )
    assert index.lookup("somme").is_validated
    assert index.lookup("diagonale").is_validated  # terme absent : ajouté
    assert summary.validated == ["triangle rectangle", "somme", "diagonale"]
    assert summary.ignored == 1


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("somme", "som", ""), "sans validateur"),
        (("somme", "SOM²", "Awa"), "caractères ignorés par le TTS : ²"),
    ],
)
def test_import_rejects_invalid_rows(row: tuple[str, str, str], message: str) -> None:
    with pytest.raises(LexiconError, match=message):
        apply_validations(LEXICON, _rows(row))


def test_export_then_import_through_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lexicon_path = tmp_path / "lexique.json"
    lexicon_path.write_text(lexicon_to_json(LEXICON), encoding="utf-8")
    csv_path = tmp_path / "a_valider.csv"
    write_validation_csv(
        csv_path, {"triangle rectangle": 5, "hypoténuse": 7, "somme": 4}, LexiconIndex(LEXICON)
    )
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[1].startswith("hypoténuse,7,ipoteniws,ipoteniws,Awa,Déjà validée.")
    assert lines[2].startswith(
        "triangle rectangle,5,tiriyaangal regtaangal,,,Proposition BROUILLON"
    )
    assert lines[3].startswith("somme,4,,,,Aucune prononciation proposée")

    lines[2] = lines[2].replace("regtaangal,,,", "regtaangal,tiriyaangal regtaangal,Moussa,")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert lexicon_cli(["import-validation", str(csv_path), "--lexicon", str(lexicon_path)]) == 0
    out = capsys.readouterr().out
    assert "2 terme(s) passé(s) au statut valide" in out  # hypoténuse (déjà) + triangle rectangle
    assert LexiconIndex(load_lexicon(lexicon_path)).lookup("triangle rectangle").is_validated
