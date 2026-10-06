from pathlib import Path

import pytest

from xamxam.eval.human import HumanEvalError, HumanRating, load_human_ratings
from xamxam.eval.metrics import (
    LAYERS,
    TOTAL,
    ErrorRate,
    Source,
    compute_term_stats,
    gain,
    global_rate,
    mean_scores,
    rank_terms,
    relative_improvement,
)
from xamxam.eval.records import Condition, TermRecord

RAW, NORMALIZED, FULL = Condition.RAW, Condition.NORMALIZED, Condition.FULL
NORMALIZATION, LEXICON = LAYERS


def _records() -> list[TermRecord]:
    # « hypoténuse » : seule la couche lexique corrige. « carré » : la normalisation suffit.
    return [
        TermRecord("P1", RAW, "hypoténuse", 2, 2),
        TermRecord("P1", NORMALIZED, "hypoténuse", 2, 2),
        TermRecord("P1", FULL, "hypoténuse", 2, 0),
        TermRecord("P2", RAW, "carré", 2, 2),
        TermRecord("P2", NORMALIZED, "carré", 2, 0),
        TermRecord("P2", FULL, "carré", 2, 0),
    ]


def test_error_rate() -> None:
    assert ErrorRate(1, 4).rate == 0.25
    assert ErrorRate().rate is None
    assert ErrorRate(1, 2) + ErrorRate(0, 2) == ErrorRate(1, 4)


def test_layer_gains_are_separated_per_term() -> None:
    stats = compute_term_stats(_records(), [])
    hyp, square = stats["hypoténuse"], stats["carré"]
    assert (hyp.layer_gain(NORMALIZATION), hyp.layer_gain(LEXICON)) == (0.0, 1.0)
    assert (square.layer_gain(NORMALIZATION), square.layer_gain(LEXICON)) == (1.0, 0.0)
    assert hyp.layer_gain(TOTAL) == square.layer_gain(TOTAL) == 1.0
    # Sans annotation, la source humaine n'a aucune donnée.
    assert hyp.rate(Source.HUMAN, FULL) is None


def test_global_rates_per_condition() -> None:
    stats = compute_term_stats(_records(), []).values()
    rates = [global_rate(stats, Source.STT, c) for c in Condition]
    assert rates == [ErrorRate(4, 4), ErrorRate(2, 4), ErrorRate(0, 4)]
    assert gain(rates[0].rate, rates[1].rate) == 0.5
    assert relative_improvement(rates[1].rate, rates[2].rate) == 1.0
    assert relative_improvement(0.0, 0.0) is None
    assert gain(None, 0.5) is None


def test_human_and_combined_rates() -> None:
    ratings = [
        # L'évaluateur entend une erreur que le STT n'a pas vue.
        HumanRating("P1", FULL, 4, 3, ("Hypoténuse", "bi")),
        HumanRating("P2", RAW, 2, 1, ()),
    ]
    stats = compute_term_stats(_records(), ratings)
    hyp = stats["hypoténuse"]
    assert hyp.get(Source.HUMAN, FULL) == ErrorRate(1, 2)
    assert hyp.get(Source.HUMAN, RAW) == ErrorRate()
    # Combiné : erreur dès qu'une des deux sources la signale.
    assert hyp.get(Source.COMBINED, FULL) == ErrorRate(1, 2)
    assert stats["carré"].get(Source.HUMAN, RAW) == ErrorRate(0, 2)
    assert stats["carré"].get(Source.COMBINED, RAW) == ErrorRate(2, 2)


def test_human_errors_are_capped_by_occurrences() -> None:
    ratings = [HumanRating("P2", FULL, None, None, ("carré", "carré", "carré"))]
    stats = compute_term_stats(_records(), ratings)
    assert stats["carré"].get(Source.HUMAN, FULL) == ErrorRate(2, 2)


def test_ranking_puts_worst_terms_first() -> None:
    records = [
        TermRecord("P1", FULL, "a", 4, 1),
        TermRecord("P1", FULL, "b", 2, 2),
        TermRecord("P1", FULL, "c", 9, 1),
        TermRecord("P2", FULL, "d", 1, 0),
    ]
    ranking = rank_terms(compute_term_stats(records, []).values())
    assert [s.term for s in ranking] == ["b", "a", "c", "d"]


def test_mean_scores() -> None:
    ratings = [
        HumanRating("P1", FULL, 4, 5, ()),
        HumanRating("P2", FULL, 2, None, ()),
        HumanRating("P1", RAW, 1, 1, ()),
    ]
    scores = mean_scores(ratings, FULL)
    assert (scores.wolof, scores.pronunciation, scores.count) == (3, 5, 2)
    assert mean_scores(ratings, NORMALIZED).count == 0


def _write_human_csv(path: Path, *rows: str) -> Path:
    header = (
        "id,condition,texte_envoye,fichier_audio,note_correction_wolof,"
        "note_prononciation_termes,mots_mal_prononces,commentaire"
    )
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_load_human_ratings_skips_empty_rows(tmp_path: Path) -> None:
    path = _write_human_csv(
        tmp_path / "h.csv",
        "P1,brut,txt,audio/P1_brut.wav,2,1,hypoténuse; triangle,",
        "P1,lexique,txt,audio/P1_lexique.wav,,,,",
    )
    [rating] = load_human_ratings(path)
    assert rating == HumanRating("P1", RAW, 2, 1, ("hypoténuse", "triangle"))


@pytest.mark.parametrize("score", ["0", "6", "bien"])
def test_load_human_ratings_rejects_bad_scores(tmp_path: Path, score: str) -> None:
    path = _write_human_csv(tmp_path / "h.csv", f"P1,brut,txt,a.wav,{score},3,,")
    with pytest.raises(HumanEvalError, match="ligne 2"):
        load_human_ratings(path)


def test_load_human_ratings_rejects_unknown_condition(tmp_path: Path) -> None:
    path = _write_human_csv(tmp_path / "h.csv", "P1,avant,txt,a.wav,3,3,,")
    with pytest.raises(HumanEvalError, match="condition inconnue"):
        load_human_ratings(path)


def test_missing_human_file_gives_no_ratings(tmp_path: Path) -> None:
    assert load_human_ratings(tmp_path / "absent.csv") == []
