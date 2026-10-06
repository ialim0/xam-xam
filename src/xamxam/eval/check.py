"""Contrôles automatiques du jeu de phrases du benchmark (python -m xamxam.eval check).

Vérifie : nombre de lignes et répartition des identifiants, présence de chaque terme cible
dans la colonne wo, nombre minimal d'occurrences et variété des positions de chaque terme,
nombre de mots, longueur après normalisation, présence de nombres et de notations. Affiche
aussi, phrase par phrase, les caractères que le TTS ignorerait (brut et normalisé).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from xamxam.eval.align import TargetTerm, tokenize
from xamxam.eval.dataset import Sentence
from xamxam.eval.run import build_target
from xamxam.pipeline import XamXamPipeline
from xamxam.tts_alphabet import unsupported_characters

# Répartition attendue des identifiants : préfixe → (notion, nombre).
EXPECTED_GROUPS = {"P": ("pythagore", 40), "T": ("thales", 40), "C": ("concret", 20)}
_WORD = re.compile(r"\w", re.UNICODE)
_RICH = re.compile(r"\d+,\d+|[²³√=/]|//")
_INTEGER = re.compile(r"\d+")


@dataclass(frozen=True)
class CheckLimits:
    expected_rows: int = 100
    min_occurrences: int = 4
    min_positions: int = 2  # positions distinctes parmi début, milieu, fin
    max_words: int = 20
    max_chars: int = 512
    min_rich_sentences: int = 60


@dataclass
class TermStats:
    occurrences: int = 0
    positions: Counter[str] = field(default_factory=Counter)


@dataclass
class SentenceReport:
    id: str
    words: int
    normalized_chars: int
    rewritten_chars: int
    lost_raw: list[str]
    lost_normalized: list[str]
    rich: bool


@dataclass
class CheckReport:
    errors: list[str]
    terms: dict[str, TermStats]
    sentences: list[SentenceReport]

    @property
    def ok(self) -> bool:
        return not self.errors


def count_words(text: str) -> int:
    """Mots = jetons séparés par des blancs contenant au moins une lettre ou un chiffre."""
    return sum(1 for token in text.split() if _WORD.search(token))


def is_rich(text: str) -> bool:
    """Nombre supérieur à 10, décimal avec virgule, ou notation mathématique."""
    if _RICH.search(text):
        return True
    return any(int(n) > 10 for n in _INTEGER.findall(text))


def _positions(tokens: Sequence[str], target: TargetTerm) -> list[str]:
    """Classe chaque occurrence en début, milieu ou fin de phrase (tiers de la phrase)."""
    candidates = sorted(
        {tuple(tokenize(f)) for f in target.source_forms} - {()}, key=len, reverse=True
    )
    found, index = [], 0
    while index < len(tokens):
        for candidate in candidates:
            if tuple(tokens[index : index + len(candidate)]) == candidate:
                center = (index + len(candidate) / 2) / max(len(tokens), 1)
                found.append("debut" if center < 1 / 3 else "fin" if center > 2 / 3 else "milieu")
                index += len(candidate)
                break
        else:
            index += 1
    return found


def check_sentences(
    sentences: Sequence[Sentence],
    pipeline: XamXamPipeline,
    limits: CheckLimits | None = None,
) -> CheckReport:
    limits = limits or CheckLimits()
    errors: list[str] = []

    if len(sentences) != limits.expected_rows:
        errors.append(f"{len(sentences)} lignes au lieu de {limits.expected_rows}.")
    for prefix, (notion, expected) in EXPECTED_GROUPS.items():
        group = [s for s in sentences if s.id.startswith(prefix)]
        wanted = {f"{prefix}{n:03d}" for n in range(1, expected + 1)}
        if {s.id for s in group} != wanted:
            errors.append(f"identifiants {prefix} : attendus {prefix}001 à {prefix}{expected:03d}.")
        wrong = [s.id for s in group if s.notion != notion]
        if wrong:
            errors.append(f"notion différente de « {notion} » : {', '.join(wrong)}.")

    terms: dict[str, TermStats] = defaultdict(TermStats)
    reports = []
    for sentence in sentences:
        tokens = tokenize(sentence.wo)
        for term in sentence.target_terms:
            target = build_target(term, pipeline.index)
            found = _positions(tokens, target)
            if not found:
                errors.append(f"{sentence.id} : terme cible « {term} » absent de la colonne wo.")
        prepared = pipeline.prepare(sentence.wo)
        words = count_words(sentence.wo)
        if words > limits.max_words:
            errors.append(f"{sentence.id} : {words} mots (maximum {limits.max_words}).")
        longest = max(len(prepared.normalized), len(prepared.text))
        if longest > limits.max_chars:
            errors.append(
                f"{sentence.id} : {longest} caractères après normalisation "
                f"(maximum {limits.max_chars})."
            )
        reports.append(
            SentenceReport(
                id=sentence.id,
                words=words,
                normalized_chars=len(prepared.normalized),
                rewritten_chars=len(prepared.text),
                lost_raw=unsupported_characters(sentence.wo),
                lost_normalized=unsupported_characters(prepared.text),
                rich=is_rich(sentence.wo),
            )
        )

    # Occurrences et positions, comptées sur toute la colonne wo pour chaque terme cible.
    all_terms = sorted({t for s in sentences for t in s.target_terms})
    for term in all_terms:
        target = build_target(term, pipeline.index)
        stats = terms[term]
        for sentence in sentences:
            found = _positions(tokenize(sentence.wo), target)
            stats.occurrences += len(found)
            stats.positions.update(found)
        if stats.occurrences < limits.min_occurrences:
            errors.append(
                f"terme « {term} » : {stats.occurrences} occurrence(s) "
                f"(minimum {limits.min_occurrences})."
            )
        if len(stats.positions) < limits.min_positions:
            errors.append(
                f"terme « {term} » : positions peu variées ({', '.join(sorted(stats.positions))})."
            )

    rich = sum(r.rich for r in reports)
    if rich < limits.min_rich_sentences:
        errors.append(
            f"{rich} phrases avec nombres > 10, décimaux ou notations "
            f"(minimum {limits.min_rich_sentences})."
        )
    return CheckReport(errors, dict(terms), reports)


def format_report(report: CheckReport) -> str:
    lines = [
        "Caractères ignorés par le TTS (brut → après Xam-Xam). Les chiffres sont signalés",
        "par prudence : le serveur Kiriku ne convertit lui-même que les nombres de 0 à 10.",
    ]
    for r in report.sentences:
        raw = " ".join(r.lost_raw) or "-"
        after = " ".join(r.lost_normalized) or "-"
        lines.append(
            f"  {r.id}  {r.words:2d} mots  {r.rewritten_chars:3d} car.  brut : {raw:<24} "
            f"après : {after}"
        )
    lines += ["", "Termes cibles (occurrences ; début / milieu / fin) :"]
    for term, stats in sorted(report.terms.items()):
        p = stats.positions
        lines.append(
            f"  {term:<24} {stats.occurrences:3d} ; {p['debut']} / {p['milieu']} / {p['fin']}"
        )
    rich = sum(r.rich for r in report.sentences)
    lines += [
        "",
        f"{len(report.sentences)} phrases, {len(report.terms)} termes cibles, "
        f"{rich} phrases avec nombres > 10, décimaux ou notations.",
    ]
    if report.ok:
        lines.append("Tous les contrôles sont passés.")
    else:
        lines.append(f"{len(report.errors)} erreur(s) :")
        lines += [f"  - {error}" for error in report.errors]
    return "\n".join(lines)
