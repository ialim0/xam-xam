"""Étape 4 (calculs) : taux d'erreur par terme, par condition et par source, apport des couches."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from statistics import mean

from xamxam.eval.human import HumanRating
from xamxam.eval.records import Condition, TermRecord


class Source(StrEnum):
    STT = "stt"
    HUMAN = "humain"
    # Erreur si au moins une des deux sources la signale.
    COMBINED = "combine"


@dataclass(frozen=True)
class Layer:
    """Une couche de Xam-Xam, mesurée par le passage d'une condition à la suivante."""

    name: str
    label: str
    start: Condition
    end: Condition


LAYERS = (
    Layer("normalisation", "Normalisation", Condition.RAW, Condition.NORMALIZED),
    Layer("lexique", "Lexique", Condition.NORMALIZED, Condition.FULL),
)
TOTAL = Layer("total", "Total Xam-Xam", Condition.RAW, Condition.FULL)


@dataclass(frozen=True)
class ErrorRate:
    errors: int = 0
    appearances: int = 0

    @property
    def rate(self) -> float | None:
        return self.errors / self.appearances if self.appearances else None

    def __add__(self, other: ErrorRate) -> ErrorRate:
        return ErrorRate(self.errors + other.errors, self.appearances + other.appearances)


def gain(before: float | None, after: float | None) -> float | None:
    """Baisse du taux d'erreur en points (positif = amélioration)."""
    return None if before is None or after is None else before - after


def relative_improvement(before: float | None, after: float | None) -> float | None:
    """Part des erreurs supprimées : (avant − après) / avant."""
    if before is None or after is None or before == 0:
        return None
    return (before - after) / before


@dataclass
class TermStats:
    term: str
    counts: dict[tuple[Source, Condition], ErrorRate] = field(
        default_factory=lambda: defaultdict(ErrorRate)
    )

    def get(self, source: Source, condition: Condition) -> ErrorRate:
        return self.counts.get((source, condition), ErrorRate())

    def rate(self, source: Source, condition: Condition) -> float | None:
        return self.get(source, condition).rate

    @property
    def appearances(self) -> int:
        return self.get(Source.STT, Condition.FULL).appearances

    def layer_gain(self, layer: Layer, source: Source = Source.COMBINED) -> float | None:
        return gain(self.rate(source, layer.start), self.rate(source, layer.end))


def compute_term_stats(
    term_records: Iterable[TermRecord], ratings: Iterable[HumanRating]
) -> dict[str, TermStats]:
    """Combine les résultats STT et les annotations humaines, terme par terme.

    La source humaine ne compte que les lignes effectivement annotées.
    """
    ratings_by_key = {(r.sentence_id, r.condition): r for r in ratings}
    stats: dict[str, TermStats] = {}
    for record in term_records:
        term_stats = stats.setdefault(record.term, TermStats(record.term))
        condition = record.condition
        term_stats.counts[(Source.STT, condition)] += ErrorRate(record.errors, record.occurrences)
        human_errors = 0
        rating = ratings_by_key.get((record.sentence_id, condition))
        if rating is not None:
            human_errors = min(rating.mentions(record.term), record.occurrences)
            term_stats.counts[(Source.HUMAN, condition)] += ErrorRate(
                human_errors, record.occurrences
            )
        term_stats.counts[(Source.COMBINED, condition)] += ErrorRate(
            max(record.errors, human_errors), record.occurrences
        )
    return stats


def global_rate(stats: Iterable[TermStats], source: Source, condition: Condition) -> ErrorRate:
    return sum((s.get(source, condition) for s in stats), ErrorRate())


def rank_terms(stats: Iterable[TermStats]) -> list[TermStats]:
    """Termes à améliorer en priorité : taux combiné final (normalisé + lexique) décroissant,
    puis nombre d'apparitions décroissant."""

    def key(s: TermStats) -> tuple[float, int, str]:
        final = s.rate(Source.COMBINED, Condition.FULL)
        return (-(final if final is not None else -1.0), -s.appearances, s.term)

    return sorted(stats, key=key)


@dataclass(frozen=True)
class MeanScores:
    wolof: float | None
    pronunciation: float | None
    count: int


def mean_scores(ratings: Sequence[HumanRating], condition: Condition) -> MeanScores:
    selected = [r for r in ratings if r.condition is condition]
    wolof = [r.wolof_score for r in selected if r.wolof_score is not None]
    pron = [r.pronunciation_score for r in selected if r.pronunciation_score is not None]
    return MeanScores(
        wolof=mean(wolof) if wolof else None,
        pronunciation=mean(pron) if pron else None,
        count=len(selected),
    )
