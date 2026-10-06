"""Alignement mot à mot entre un texte de référence et une transcription."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

_TOKEN = re.compile(r"\w+(?:['’-]\w+)*")


def tokenize(text: str) -> list[str]:
    """Découpe en mots minuscules sans ponctuation ; apostrophes et tirets internes conservés."""
    return [token.casefold() for token in _TOKEN.findall(unicodedata.normalize("NFC", text))]


class EditOp(StrEnum):
    EQUAL = "equal"
    SUBSTITUTE = "substitute"
    DELETE = "delete"  # mot de la référence absent de la transcription
    INSERT = "insert"  # mot ajouté par la transcription


@dataclass(frozen=True)
class AlignedPair:
    op: EditOp
    reference: str | None
    hypothesis: str | None


def align_words(reference: Sequence[str], hypothesis: Sequence[str]) -> list[AlignedPair]:
    """Alignement de Levenshtein mot à mot (coût 1 par substitution, suppression, insertion)."""
    rows, cols = len(reference) + 1, len(hypothesis) + 1
    cost = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        cost[i][0] = i
    for j in range(cols):
        cost[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            same = reference[i - 1] == hypothesis[j - 1]
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if same else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )

    # Remontée du chemin optimal, de la fin vers le début.
    pairs: list[AlignedPair] = []
    i, j = len(reference), len(hypothesis)
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = reference[i - 1] == hypothesis[j - 1]
            if cost[i][j] == cost[i - 1][j - 1] + (0 if same else 1):
                op = EditOp.EQUAL if same else EditOp.SUBSTITUTE
                pairs.append(AlignedPair(op, reference[i - 1], hypothesis[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append(AlignedPair(EditOp.DELETE, reference[i - 1], None))
            i -= 1
        else:
            pairs.append(AlignedPair(EditOp.INSERT, None, hypothesis[j - 1]))
            j -= 1
    pairs.reverse()
    return pairs


def word_error_rate(alignment: Sequence[AlignedPair]) -> float:
    """Taux d'erreur mot (WER) : erreurs / nombre de mots de la référence."""
    reference_length = sum(1 for pair in alignment if pair.reference is not None)
    errors = sum(1 for pair in alignment if pair.op is not EditOp.EQUAL)
    if reference_length == 0:
        return 0.0 if errors == 0 else 1.0
    return errors / reference_length


def count_occurrences(tokens: Sequence[str], forms: Iterable[str]) -> int:
    """Compte les occurrences non chevauchantes des graphies, la plus longue d'abord."""
    candidates = sorted({tuple(tokenize(form)) for form in forms} - {()}, key=len, reverse=True)
    count, position = 0, 0
    while position < len(tokens):
        for candidate in candidates:
            if tuple(tokens[position : position + len(candidate)]) == candidate:
                count += 1
                position += len(candidate)
                break
        else:
            position += 1
    return count


@dataclass(frozen=True)
class TargetTerm:
    """Terme cible et graphies acceptées dans la source et dans la transcription."""

    term: str
    source_forms: tuple[str, ...]
    # Graphies considérées comme une bonne restitution (terme, alias, prononciation du lexique).
    accepted_forms: tuple[str, ...]


@dataclass(frozen=True)
class TermCheck:
    term: str
    occurrences: int
    errors: int


def check_target_terms(
    source: str, transcript: str, targets: Iterable[TargetTerm]
) -> list[TermCheck]:
    """Pour chaque terme cible : apparitions dans la source et nombre de restitutions manquées."""
    source_tokens = tokenize(source)
    transcript_tokens = tokenize(transcript)
    checks = []
    for target in targets:
        # Un terme déclaré cible compte au moins une fois, même si sa graphie diffère.
        occurrences = max(1, count_occurrences(source_tokens, target.source_forms))
        found = count_occurrences(transcript_tokens, target.accepted_forms)
        checks.append(TermCheck(target.term, occurrences, max(0, occurrences - found)))
    return checks
