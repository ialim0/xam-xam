import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from xamxam.lexicon import Lexicon, LexiconError, LexiconIndex, Term, load_lexicon


def _lexicon(*terms: dict) -> Lexicon:
    return Lexicon.model_validate({"version": "test", "language": "wo", "terms": list(terms)})


def test_example_lexicon_is_valid(lexicon: Lexicon) -> None:
    assert lexicon.language == "wo"
    assert len(lexicon.terms) == 5


def test_duplicate_forms_are_rejected() -> None:
    with pytest.raises(ValidationError, match="déclarée deux fois"):
        _lexicon(
            {"term": "triangle", "pronunciation": "a"},
            {"term": "polygone", "pronunciation": "b", "aliases": ["Triangle"]},
        )


@pytest.mark.parametrize(
    "entry",
    [
        {"term": "  ", "pronunciation": "a"},
        {"term": "a", "pronunciation": ""},
        {"term": "a", "pronunciation": "b", "aliases": [" "]},
        {"term": "a", "pronunciation": "b", "unknown_field": 1},
    ],
)
def test_invalid_terms_are_rejected(entry: dict) -> None:
    with pytest.raises(ValidationError):
        Term.model_validate(entry)


def test_load_lexicon_reports_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "lexique.json"
    path.write_text(json.dumps({"version": "1", "language": "wo"}), encoding="utf-8")
    with pytest.raises(LexiconError, match="Lexique invalide"):
        load_lexicon(path)


def test_load_lexicon_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LexiconError, match="Impossible de lire"):
        load_lexicon(tmp_path / "absent.json")


def test_lookup_ignores_case_and_spacing(index: LexiconIndex) -> None:
    term = index.lookup("  Triangle   RECTANGLE ")
    assert term is not None and term.term == "triangle rectangle"
    assert index.lookup("parallèles").term == "parallèle"
    assert index.lookup("cercle") is None


def test_compound_term_has_priority(index: LexiconIndex) -> None:
    matches = index.find_all("Un triangle rectangle et un triangle.")
    assert [m.term.term for m in matches] == ["triangle rectangle", "triangle"]
    assert matches[0].surface == "triangle rectangle"


def test_matching_respects_word_boundaries() -> None:
    index = LexiconIndex(_lexicon({"term": "angle", "pronunciation": "x"}))
    assert index.find_all("rectangle, triangle") == []
    assert len(index.find_all("un angle droit")) == 1


def test_compound_term_tolerates_line_breaks(index: LexiconIndex) -> None:
    matches = index.find_all("triangle\n  rectangle")
    assert [m.term.term for m in matches] == ["triangle rectangle"]


def test_empty_lexicon_finds_nothing() -> None:
    assert LexiconIndex(_lexicon()).find_all("triangle") == []
