"""Étape 4 (calculs) : taux d'erreur par terme, avant/après, par source."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from statistics import mean

from xamxam.eval.human import HumanRating
from xamxam.eval.records import TermRecord, Version


class Source(StrEnum):
    STT = "stt"
    HUMAN = "humain"
    # Erreur si au moins une des deux sources la signale.
    COMBINED = "combine"


@dataclass(frozen=True)
class ErrorRate:
    errors: int = 0
    appearances: int = 0

    @property
    def rate(self) -> float | None:
        return self.errors / self.appearances if self.appearances else None

    def __add__(self, other: ErrorRate) -> ErrorRate:
        return ErrorRate(self.errors + other.errors, self.appearances + other.appearances)


@dataclass
class TermStats:
    term: str
    counts: dict[tuple[Source, Version], ErrorRate] = field(
        default_factory=lambda: defaultdict(ErrorRate)
    )

    def get(self, source: Source, version: Version) -> ErrorRate:
        return self.counts.get((source, version), ErrorRate())

    def rate(self, source: Source, version: Version) -> float | None:
        return self.get(source, version).rate

    @property
    def appearances(self) -> int:
        return self.get(Source.STT, Version.AFTER).appearances

    def improvement(self, source: Source = Source.COMBINED) -> float | None:
        """Baisse du taux d'erreur en points (avant − après)."""
        before, after = self.rate(source, Version.BEFORE), self.rate(source, Version.AFTER)
        return None if before is None or after is None else before - after


def compute_term_stats(
    term_records: Iterable[TermRecord], ratings: Iterable[HumanRating]
) -> dict[str, TermStats]:
    """Combine les résultats STT et les annotations humaines, terme par terme.

    La source humaine ne compte que les phrases effectivement annotées.
    """
    ratings_by_key = {(r.sentence_id, r.version): r for r in ratings}
    stats: dict[str, TermStats] = {}
    for record in term_records:
        term_stats = stats.setdefault(record.term, TermStats(record.term))
        key = (record.sentence_id, record.version)
        term_stats.counts[(Source.STT, record.version)] += ErrorRate(
            record.errors, record.occurrences
        )
        human_errors = 0
        rating = ratings_by_key.get(key)
        if rating is not None:
            human_errors = min(rating.mentions(record.term), record.occurrences)
            term_stats.counts[(Source.HUMAN, record.version)] += ErrorRate(
                human_errors, record.occurrences
            )
        term_stats.counts[(Source.COMBINED, record.version)] += ErrorRate(
            max(record.errors, human_errors), record.occurrences
        )
    return stats


def global_rate(stats: Iterable[TermStats], source: Source, version: Version) -> ErrorRate:
    return sum((s.get(source, version) for s in stats), ErrorRate())


def relative_improvement(before: float | None, after: float | None) -> float | None:
    """Part des erreurs supprimées : (avant − après) / avant."""
    if before is None or after is None or before == 0:
        return None
    return (before - after) / before


def rank_terms(stats: Iterable[TermStats]) -> list[TermStats]:
    """Termes à améliorer en priorité : taux combiné après Xam-Xam décroissant,
    puis nombre d'apparitions décroissant."""

    def key(s: TermStats) -> tuple[float, int, str]:
        after = s.rate(Source.COMBINED, Version.AFTER)
        return (-(after if after is not None else -1.0), -s.appearances, s.term)

    return sorted(stats, key=key)


@dataclass(frozen=True)
class MeanScores:
    wolof: float | None
    pronunciation: float | None
    count: int


def mean_scores(ratings: Sequence[HumanRating], version: Version) -> MeanScores:
    selected = [r for r in ratings if r.version is version]
    wolof = [r.wolof_score for r in selected if r.wolof_score is not None]
    pron = [r.pronunciation_score for r in selected if r.pronunciation_score is not None]
    return MeanScores(
        wolof=mean(wolof) if wolof else None,
        pronunciation=mean(pron) if pron else None,
        count=len(selected),
    )
