"""Étape 4 (sorties) : classement des termes en CSV et résumé en Markdown."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from xamxam.audio_feedback import check_math_audio
from xamxam.eval.human import HumanRating, load_human_ratings
from xamxam.eval.metrics import (
    LAYERS,
    TOTAL,
    Source,
    TermStats,
    compute_term_stats,
    gain,
    global_rate,
    mean_scores,
    rank_terms,
    relative_improvement,
)
from xamxam.eval.records import (
    Condition,
    OutputPaths,
    RunInfo,
    TermRecord,
    TranscriptionRecord,
    read_terms,
    read_transcriptions,
)

TOP_TERMS_IN_SUMMARY = 10
_SOURCE_LABELS = {Source.STT: "STT", Source.HUMAN: "Humain", Source.COMBINED: "Combiné"}
_RANKING_COLUMNS = (
    "rang",
    "terme",
    "apparitions",
    *(f"taux_{c}_{s}" for s in Source for c in Condition),
    *(f"apport_{layer.name}_combine" for layer in (*LAYERS, TOTAL)),
)


@dataclass(frozen=True)
class Report:
    ranking: list[TermStats]
    ratings: list[HumanRating]
    transcriptions: list[TranscriptionRecord]
    run_info: RunInfo | None = None


def build_report(paths: OutputPaths) -> Report:
    """Lit les résultats de `run` (et la fiche humaine si elle existe), puis écrit le rapport."""
    transcriptions = read_transcriptions(paths.transcriptions_csv)
    ratings = load_human_ratings(paths.human_csv)
    terms = read_terms(paths.terms_csv)
    stats = compute_term_stats(terms, ratings)
    report = Report(
        rank_terms(stats.values()), ratings, transcriptions, RunInfo.read(paths.run_info_json)
    )
    write_ranking(paths.ranking_csv, report.ranking)
    write_math_feedback(paths.math_feedback_csv, transcriptions)
    write_phrase_diagnostic(paths.phrase_diagnostic_csv, transcriptions, terms)
    paths.summary_md.parent.mkdir(parents=True, exist_ok=True)
    paths.summary_md.write_text(render_summary(report), encoding="utf-8")
    return report


def write_phrase_diagnostic(
    path: Path, records: list[TranscriptionRecord], terms: list[TermRecord]
) -> None:
    """Classe les phrases selon les indices STT, pour orienter l'écoute humaine."""
    by_id = {(record.sentence_id, record.condition): record for record in records}
    term_rows: dict[tuple[str, Condition], list[TermRecord]] = {}
    for term in terms:
        term_rows.setdefault((term.sentence_id, term.condition), []).append(term)

    columns = ["id", "texte_source"]
    for condition in (Condition.NORMALIZED, Condition.FULL):
        suffix = str(condition)
        columns.extend(
            (
                f"elements_formule_non_reperes_stt_{suffix}",
                f"details_formule_{suffix}",
                f"termes_non_reperes_stt_{suffix}",
                f"details_termes_{suffix}",
                f"wer_{suffix}",
                f"transcription_{suffix}",
                f"audio_{suffix}",
            )
        )

    rows: list[dict[str, object]] = []
    for raw in records:
        if raw.condition is not Condition.RAW:
            continue
        row: dict[str, object] = {"id": raw.sentence_id, "texte_source": raw.sent_text}
        for condition in (Condition.NORMALIZED, Condition.FULL):
            record = by_id[(raw.sentence_id, condition)]
            checks = check_math_audio(raw.sent_text, record.transcript)
            missed_terms = [
                term for term in term_rows.get((raw.sentence_id, condition), []) if term.errors
            ]
            suffix = str(condition)
            row[f"elements_formule_non_reperes_stt_{suffix}"] = sum(
                check.missing for check in checks
            )
            row[f"details_formule_{suffix}"] = "; ".join(
                f"{check.kind} {check.value} x{check.missing}" for check in checks if check.missing
            )
            row[f"termes_non_reperes_stt_{suffix}"] = sum(term.errors for term in missed_terms)
            row[f"details_termes_{suffix}"] = "; ".join(
                f"{term.term} x{term.errors}" for term in missed_terms
            )
            row[f"wer_{suffix}"] = f"{record.wer:.4f}"
            row[f"transcription_{suffix}"] = record.transcript
            row[f"audio_{suffix}"] = record.audio_file
        rows.append(row)

    rows.sort(
        key=lambda row: (
            -int(row["elements_formule_non_reperes_stt_normalise"]),
            -int(row["termes_non_reperes_stt_normalise"]),
            -float(row["wer_normalise"]),
            str(row["id"]),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_math_feedback(path: Path, records: list[TranscriptionRecord]) -> None:
    """Signale les éléments de formule non retrouvés par le STT, sans confondre BC et bee see."""
    sources = {
        record.sentence_id: record.sent_text
        for record in records
        if record.condition is Condition.RAW
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("id", "condition", "element", "valeur", "attendu", "reconnu", "manquant"))
        for record in records:
            if record.condition is Condition.RAW:
                continue
            for check in check_math_audio(sources[record.sentence_id], record.transcript):
                writer.writerow(
                    (
                        record.sentence_id,
                        record.condition,
                        check.kind,
                        check.value,
                        check.expected,
                        check.heard,
                        check.missing,
                    )
                )


def _csv_number(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


def write_ranking(path: Path, ranking: list[TermStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(_RANKING_COLUMNS)
        for position, stats in enumerate(ranking, start=1):
            writer.writerow(
                (
                    position,
                    stats.term,
                    stats.appearances,
                    *(_csv_number(stats.rate(s, c)) for s in Source for c in Condition),
                    *(_csv_number(stats.layer_gain(layer)) for layer in (*LAYERS, TOTAL)),
                )
            )


def _french_decimal(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _percent(value: float | None) -> str:
    return "n/d" if value is None else f"{_french_decimal(value * 100, 1)} %"


def _points(value: float | None) -> str:
    return "n/d" if value is None else f"{value * 100:+.1f} pts".replace(".", ",")


def _score(value: float | None) -> str:
    return "n/d" if value is None else _french_decimal(value, 2)


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def _table(header: list[str]) -> list[str]:
    return [_row(*header), _row(*(["---"] * len(header)))]


_NUMBER_LANGUAGES = {"fr": "français", "wo": "wolof"}
_LEXICON_STATUSES = {
    "valide": "prononciations validées uniquement",
    "brouillon": "prononciations validées et brouillons",
}


def _run_parameters(info: RunInfo | None) -> list[str]:
    """Paramètres du run : langue des nombres et origine des prononciations appliquées."""
    if info is None:
        return ["_Paramètres du run inconnus (run_info.json absent)._", ""]
    validated = info.applied.get("valide")
    draft = info.applied.get("brouillon")

    def describe(applied) -> str:  # type: ignore[no-untyped-def]
        if applied is None or applied.occurrences == 0:
            return "0 occurrence"
        return f"{applied.occurrences} occurrence(s), {len(applied.terms)} terme(s)"

    number_language = _NUMBER_LANGUAGES.get(info.number_language, info.number_language)
    lexicon_status = _LEXICON_STATUSES.get(info.lexicon_status, info.lexicon_status)
    lines = [
        "## Paramètres du run",
        "",
        f"- Langue des nombres : **{number_language}** "
        f"(`--number-language {info.number_language}`)",
        f"- Lexique : **{lexicon_status}** (`--lexique-statut {info.lexicon_status}`)",
        f"- Termes appliqués avec une prononciation **validée** : {describe(validated)}",
        f"- Termes appliqués avec une prononciation **brouillon** : {describe(draft)}",
    ]
    if draft is not None and draft.occurrences:
        lines.append(
            "- ⚠️ Des prononciations brouillon ont été appliquées : les résultats de la "
            "condition « lexique » ne reflètent pas un lexique validé."
        )
    return [*lines, ""]


def render_summary(report: Report) -> str:
    sentence_count = len({t.sentence_id for t in report.transcriptions})
    conditions = list(Condition)
    lines = [
        "# Rapport d'évaluation Xam-Xam",
        "",
        f"- Phrases évaluées : {sentence_count}",
        f"- Lignes annotées par des évaluateurs humains : {len(report.ratings)}",
        "- Conditions : "
        + ", ".join(f"**{c.label}** (`{c}`)" for c in conditions)
        + ". Chacune ajoute une couche à la précédente.",
        "",
        *_run_parameters(report.run_info),
        "## Taux d'erreur sur les termes cibles",
        "",
        *_table(["Source", *(c.label for c in conditions)]),
    ]
    for source in Source:
        lines.append(
            _row(
                _SOURCE_LABELS[source],
                *(_percent(global_rate(report.ranking, source, c).rate) for c in conditions),
            )
        )

    lines += [
        "",
        "La source « Combiné » compte une erreur dès que le STT ou un évaluateur la signale.",
        "",
        "## Apport de chaque couche (source combinée)",
        "",
        *_table(["Couche", "Taux avant", "Taux après", "Gain", "Erreurs supprimées"]),
    ]
    for layer in (*LAYERS, TOTAL):
        before = global_rate(report.ranking, Source.COMBINED, layer.start).rate
        after = global_rate(report.ranking, Source.COMBINED, layer.end).rate
        lines.append(
            _row(
                f"{layer.label} ({layer.start.label} → {layer.end.label})",
                _percent(before),
                _percent(after),
                _points(gain(before, after)),
                _percent(relative_improvement(before, after)),
            )
        )

    sources = {
        record.sentence_id: record.sent_text
        for record in report.transcriptions
        if record.condition is Condition.RAW
    }
    lines += [
        "",
        "## Éléments mathématiques retrouvés par le STT",
        "",
        *_table(["Condition", "Éléments reconnus", "Éléments attendus", "Phrases avec manque"]),
    ]
    for condition in (Condition.NORMALIZED, Condition.FULL):
        checks_by_phrase = [
            check_math_audio(sources[record.sentence_id], record.transcript)
            for record in report.transcriptions
            if record.condition is condition
        ]
        lines.append(
            _row(
                condition.label,
                sum(check.heard for checks in checks_by_phrase for check in checks),
                sum(check.expected for checks in checks_by_phrase for check in checks),
                sum(any(check.missing for check in checks) for checks in checks_by_phrase),
            )
        )
    lines += [
        "",
        "Les graphies d'un même nom de point (par exemple `BC` et `bee see`) sont regroupées. "
        "Un manque signalé par le STT peut aussi venir d'une erreur de reconnaissance.",
    ]

    lines += [
        "",
        "## WER moyen de l'aller-retour TTS → STT",
        "",
        *_table([c.label for c in conditions]),
        _row(
            *(
                _percent(mean(wers) if wers else None)
                for wers in (
                    [t.wer for t in report.transcriptions if t.condition is c] for c in conditions
                )
            )
        ),
        "",
        "## Notes humaines moyennes (1 à 5)",
        "",
        *_table(["Condition", "Lignes", "Correction du wolof", "Prononciation des termes"]),
    ]
    for condition in conditions:
        scores = mean_scores(report.ratings, condition)
        lines.append(
            _row(
                condition.label,
                scores.count,
                _score(scores.wolof),
                _score(scores.pronunciation),
            )
        )

    lines += [
        "",
        f"## Termes à améliorer en priorité (top {TOP_TERMS_IN_SUMMARY})",
        "",
        *_table(
            [
                "Rang",
                "Terme",
                "Apparitions",
                *(c.label for c in conditions),
                *(f"Apport {layer.name}" for layer in LAYERS),
            ]
        ),
    ]
    for position, stats in enumerate(report.ranking[:TOP_TERMS_IN_SUMMARY], start=1):
        lines.append(
            _row(
                position,
                stats.term,
                stats.appearances,
                *(_percent(stats.rate(Source.COMBINED, c)) for c in conditions),
                *(_points(stats.layer_gain(layer)) for layer in LAYERS),
            )
        )
    lines += [
        "",
        "Classement complet : `rapport/classement_termes.csv`.",
        "Diagnostic des phrases : `rapport/diagnostic_phrases.csv`, classé par éléments "
        "mathématiques puis termes non repérés par le STT dans la version normalisée.",
        "",
    ]
    return "\n".join(lines)
