"""Fichier de validation des termes cibles par des locuteurs natifs.

export : génère termes_cibles_a_valider.csv (une ligne par terme cible du jeu de phrases).
import : relit le fichier rempli et met à jour le lexique ; une ligne avec une
prononciation validée ET un validateur passe le terme au statut « valide ».
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from xamxam.lexicon.index import LexiconIndex
from xamxam.lexicon.loader import LexiconError
from xamxam.lexicon.schema import Lexicon, Term, TermStatus
from xamxam.tts_alphabet import unsupported_characters

VALIDATION_COLUMNS = (
    "terme",
    "nombre_occurrences",
    "prononciation_proposee",
    "prononciation_validee",
    "validateur",
    "remarques",
)
DRAFT_REMARK = "Proposition BROUILLON (non validée) : à corriger ou confirmer."
MISSING_REMARK = "Aucune prononciation proposée : à compléter."


@dataclass(frozen=True)
class ImportSummary:
    validated: list[str]
    ignored: int  # lignes sans prononciation validée


def _remark(*, validated: bool, proposed: bool) -> str:
    if validated:
        return "Déjà validée."
    return DRAFT_REMARK if proposed else MISSING_REMARK


def write_validation_csv(path: Path, occurrences: dict[str, int], index: LexiconIndex) -> None:
    """Une ligne par terme cible, triée par nombre d'occurrences décroissant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(VALIDATION_COLUMNS)
        for term, count in sorted(occurrences.items(), key=lambda kv: (-kv[1], kv[0])):
            entry = index.lookup(term)
            proposed = entry.pronunciation if entry and entry.pronunciation else ""
            validated = entry.pronunciation if entry and entry.is_validated else ""
            validator = entry.validated_by if entry and entry.is_validated else ""
            remark = _remark(validated=bool(validated), proposed=bool(proposed))
            writer.writerow((term, count, proposed, validated, validator, remark))


def read_validation_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            missing = set(VALIDATION_COLUMNS) - set(reader.fieldnames or ())
            if missing:
                raise LexiconError(f"{path} : colonnes manquantes : {', '.join(sorted(missing))}")
            return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]
    except OSError as exc:
        raise LexiconError(f"Impossible de lire {path} : {exc}") from exc


def apply_validations(
    lexicon: Lexicon, rows: Iterable[dict[str, str]], *, source: str = "fichier"
) -> tuple[Lexicon, ImportSummary]:
    """Met à jour le lexique : statut valide pour chaque ligne validée et signée."""
    by_form = {form.casefold(): i for i, t in enumerate(lexicon.terms) for form in t.forms}
    terms = list(lexicon.terms)
    validated, ignored, errors = [], 0, []
    for line, row in enumerate(rows, start=2):
        term, pronunciation, validator = (
            row["terme"],
            row["prononciation_validee"],
            row["validateur"],
        )
        if not pronunciation:
            ignored += 1
            continue
        if not validator:
            errors.append(f"ligne {line} (« {term} ») : prononciation validée sans validateur")
            continue
        lost = unsupported_characters(pronunciation, lexicon.language)
        if lost:
            errors.append(
                f"ligne {line} (« {term} ») : caractères ignorés par le TTS : {' '.join(lost)}"
            )
            continue
        update = {
            "pronunciation": pronunciation,
            "status": TermStatus.VALIDATED,
            "validated_by": validator,
        }
        remark = row.get("remarques", "")
        position = by_form.get(term.casefold())
        if position is None:
            terms.append(Term.model_validate({"term": term, **update, "notes": remark}))
            by_form[term.casefold()] = len(terms) - 1
        else:
            current = terms[position]
            notes = remark if remark and remark != DRAFT_REMARK else current.notes
            terms[position] = Term.model_validate(
                {**current.model_dump(by_alias=False), **update, "notes": notes}
            )
        validated.append(term)
    if errors:
        raise LexiconError(f"Import refusé ({source}) :\n  " + "\n  ".join(errors))
    updated = Lexicon.model_validate(
        {"version": lexicon.version, "language": lexicon.language, "terms": terms}
    )
    return updated, ImportSummary(validated, ignored)
