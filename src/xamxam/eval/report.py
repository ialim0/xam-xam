"""Étape 4 (sorties) : classement des termes en CSV et résumé en Markdown."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from xamxam.eval.human import HumanRating, load_human_ratings
from xamxam.eval.metrics import (
    Source,
    TermStats,
    compute_term_stats,
    global_rate,
    mean_scores,
    rank_terms,
    relative_improvement,
)
from xamxam.eval.records import (
    OutputPaths,
    TranscriptionRecord,
    Version,
    read_terms,
    read_transcriptions,
)

TOP_TERMS_IN_SUMMARY = 10
_RANKING_COLUMNS = (
    "rang",
    "terme",
    "apparitions",
    *(f"taux_{v}_{s}" for s in Source for v in Version),
    "amelioration_combine",
)


@dataclass(frozen=True)
class Report:
    ranking: list[TermStats]
    ratings: list[HumanRating]
    transcriptions: list[TranscriptionRecord]


def build_report(paths: OutputPaths) -> Report:
    """Lit les résultats de `run` (et la fiche humaine si elle existe), puis écrit le rapport."""
    transcriptions = read_transcriptions(paths.transcriptions_csv)
    ratings = load_human_ratings(paths.human_csv)
    stats = compute_term_stats(read_terms(paths.terms_csv), ratings)
    report = Report(rank_terms(stats.values()), ratings, transcriptions)
    write_ranking(paths.ranking_csv, report.ranking)
    paths.summary_md.parent.mkdir(parents=True, exist_ok=True)
    paths.summary_md.write_text(render_summary(report), encoding="utf-8")
    return report


def _csv_number(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


def write_ranking(path: Path, ranking: list[TermStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(_RANKING_COLUMNS)
        for position, stats in enumerate(ranking, start=1):
            writer.writerow(
                (
                    position,
                    stats.term,
                    stats.appearances,
                    *(_csv_number(stats.rate(s, v)) for s in Source for v in Version),
                    _csv_number(stats.improvement()),
                )
            )


def _percent(value: float | None) -> str:
    return "n/d" if value is None else f"{value * 100:.1f} %".replace(".", ",")


def _score(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.2f}".replace(".", ",")


def render_summary(report: Report) -> str:
    sentence_count = len({t.sentence_id for t in report.transcriptions})
    lines = [
        "# Rapport d'évaluation Xam-Xam",
        "",
        f"- Phrases évaluées : {sentence_count}",
        f"- Lignes annotées par des évaluateurs humains : {len(report.ratings)}",
        "",
        "## Taux d'erreur global sur les termes cibles",
        "",
        "| Source | Avant | Après | Amélioration relative |",
        "| --- | --- | --- | --- |",
    ]
    labels = {Source.STT: "STT", Source.HUMAN: "Humain", Source.COMBINED: "Combiné"}
    for source in Source:
        before = global_rate(report.ranking, source, Version.BEFORE).rate
        after = global_rate(report.ranking, source, Version.AFTER).rate
        lines.append(
            f"| {labels[source]} | {_percent(before)} | {_percent(after)} "
            f"| {_percent(relative_improvement(before, after))} |"
        )

    lines += [
        "",
        "La source « Combiné » compte une erreur dès que le STT ou un évaluateur la signale.",
        "",
        "## WER moyen de l'aller-retour TTS → STT",
        "",
        "| Avant | Après |",
        "| --- | --- |",
        "| {} | {} |".format(
            *(
                _percent(mean(wers) if wers else None)
                for wers in (
                    [t.wer for t in report.transcriptions if t.version is v] for v in Version
                )
            )
        ),
        "",
        "## Notes humaines moyennes (1 à 5)",
        "",
        "| Version | Lignes | Correction du wolof | Prononciation des termes |",
        "| --- | --- | --- | --- |",
    ]
    for version in Version:
        scores = mean_scores(report.ratings, version)
        lines.append(
            f"| {version} | {scores.count} | {_score(scores.wolof)} "
            f"| {_score(scores.pronunciation)} |"
        )

    lines += [
        "",
        f"## Termes à améliorer en priorité (top {TOP_TERMS_IN_SUMMARY})",
        "",
        "| Rang | Terme | Apparitions | Taux avant | Taux après |",
        "| --- | --- | --- | --- | --- |",
    ]
    for position, stats in enumerate(report.ranking[:TOP_TERMS_IN_SUMMARY], start=1):
        lines.append(
            f"| {position} | {stats.term} | {stats.appearances} "
            f"| {_percent(stats.rate(Source.COMBINED, Version.BEFORE))} "
            f"| {_percent(stats.rate(Source.COMBINED, Version.AFTER))} |"
        )
    lines += ["", "Classement complet : `rapport/classement_termes.csv`.", ""]
    return "\n".join(lines)
