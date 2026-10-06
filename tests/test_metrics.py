from pathlib import Path

import pytest

from xamxam.eval.human import HumanEvalError, HumanRating, load_human_ratings
from xamxam.eval.metrics import (
    ErrorRate,
    Source,
    compute_term_stats,
    global_rate,
    mean_scores,
    rank_terms,
    relative_improvement,
)
from xamxam.eval.records import TermRecord, Version

BEFORE, AFTER = Version.BEFORE, Version.AFTER


def _records() -> list[TermRecord]:
    return [
        TermRecord("P1", BEFORE, "hypoténuse", 2, 2),
        TermRecord("P1", AFTER, "hypoténuse", 2, 0),
        TermRecord("P2", BEFORE, "hypoténuse", 1, 1),
        TermRecord("P2", AFTER, "hypoténuse", 1, 0),
        TermRecord("P2", BEFORE, "triangle", 1, 0),
        TermRecord("P2", AFTER, "triangle", 1, 0),
    ]


def test_error_rate() -> None:
    assert ErrorRate(1, 4).rate == 0.25
    assert ErrorRate().rate is None
    assert ErrorRate(1, 2) + ErrorRate(0, 2) == ErrorRate(1, 4)


def test_stt_only_rates() -> None:
    stats = compute_term_stats(_records(), [])
    hyp = stats["hypoténuse"]
    assert hyp.rate(Source.STT, BEFORE) == 1.0
    assert hyp.rate(Source.STT, AFTER) == 0.0
    assert hyp.improvement(Source.STT) == 1.0
    assert hyp.appearances == 3
    # Sans annotation, la source humaine n'a aucune donnée.
    assert hyp.rate(Source.HUMAN, AFTER) is None
    assert hyp.rate(Source.COMBINED, AFTER) == 0.0


def test_human_and_combined_rates() -> None:
    ratings = [
        # L'évaluateur entend une erreur que le STT n'a pas vue.
        HumanRating("P2", AFTER, 4, 3, ("Hypoténuse", "bi")),
        HumanRating("P2", BEFORE, 2, 1, ()),
    ]
    stats = compute_term_stats(_records(), ratings)
    hyp = stats["hypoténuse"]
    assert hyp.get(Source.HUMAN, AFTER) == ErrorRate(1, 1)
    assert hyp.get(Source.HUMAN, BEFORE) == ErrorRate(0, 1)
    # Combiné : erreur dès qu'une des deux sources la signale.
    assert hyp.get(Source.COMBINED, AFTER) == ErrorRate(1, 3)
    assert hyp.get(Source.COMBINED, BEFORE) == ErrorRate(3, 3)


def test_human_errors_are_capped_by_occurrences() -> None:
    ratings = [HumanRating("P2", AFTER, None, None, ("triangle", "triangle"))]
    stats = compute_term_stats(_records(), ratings)
    assert stats["triangle"].get(Source.HUMAN, AFTER) == ErrorRate(1, 1)


def test_global_rate_and_improvement() -> None:
    stats = compute_term_stats(_records(), []).values()
    before = global_rate(stats, Source.STT, BEFORE)
    after = global_rate(stats, Source.STT, AFTER)
    assert before == ErrorRate(3, 4)
    assert after == ErrorRate(0, 4)
    assert relative_improvement(before.rate, after.rate) == 1.0
    assert relative_improvement(0.0, 0.0) is None
    assert relative_improvement(None, 0.5) is None


def test_ranking_puts_worst_terms_first() -> None:
    records = [
        TermRecord("P1", AFTER, "a", 4, 1),
        TermRecord("P1", AFTER, "b", 2, 2),
        TermRecord("P1", AFTER, "c", 9, 1),
        TermRecord("P2", AFTER, "d", 1, 0),
    ]
    ranking = rank_terms(compute_term_stats(records, []).values())
    assert [s.term for s in ranking] == ["b", "a", "c", "d"]


def test_mean_scores() -> None:
    ratings = [
        HumanRating("P1", AFTER, 4, 5, ()),
        HumanRating("P2", AFTER, 2, None, ()),
        HumanRating("P1", BEFORE, 1, 1, ()),
    ]
    scores = mean_scores(ratings, AFTER)
    assert (scores.wolof, scores.pronunciation, scores.count) == (3, 5, 2)


def _write_human_csv(path: Path, *rows: str) -> Path:
    header = (
        "id,version,texte_envoye,fichier_audio,note_correction_wolof,"
        "note_prononciation_termes,mots_mal_prononces,commentaire"
    )
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_load_human_ratings_skips_empty_rows(tmp_path: Path) -> None:
    path = _write_human_csv(
        tmp_path / "h.csv",
        "P1,avant,txt,audio/P1_avant.wav,2,1,hypoténuse; triangle,",
        "P1,apres,txt,audio/P1_apres.wav,,,,",
    )
    [rating] = load_human_ratings(path)
    assert rating == HumanRating("P1", BEFORE, 2, 1, ("hypoténuse", "triangle"))


@pytest.mark.parametrize("score", ["0", "6", "bien"])
def test_load_human_ratings_rejects_bad_scores(tmp_path: Path, score: str) -> None:
    path = _write_human_csv(tmp_path / "h.csv", f"P1,avant,txt,a.wav,{score},3,,")
    with pytest.raises(HumanEvalError, match="ligne 2"):
        load_human_ratings(path)


def test_missing_human_file_gives_no_ratings(tmp_path: Path) -> None:
    assert load_human_ratings(tmp_path / "absent.csv") == []
