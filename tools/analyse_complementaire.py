"""Analyse complémentaire du benchmark 100, à partir des seuls CSV publiés (aucune API).

Le WER publié compare chaque transcription au texte envoyé *dans sa condition* : la
référence change d'une condition à l'autre et « douze » entendu « 12 » compte comme une
erreur. Les deux mesures ci-dessous utilisent au contraire une référence commune, la phrase
d'origine, pour les trois conditions :

- nombres retrouvés : chaque nombre de l'énoncé (« 8,6 » compte pour 8 et 6) est cherché
  dans la transcription, écrit en chiffres ou en toutes lettres (français) ;
- éléments de formule : noms de points, carrés, signes égal, plus et racines, avec le
  contrôle du bot (`check_math_audio`), étendu à la condition brute.

Usage : python tools/analyse_complementaire.py [dossier_du_run]
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from xamxam.audio_feedback import check_math_audio
from xamxam.normalize.numbers import spell_french_number

CONDITIONS = ("brut", "normalise", "lexique")
LABELS = {"brut": "Texte brut", "normalise": "Normalisé", "lexique": "Normalisé + lexique"}
_DIGITS = re.compile(r"\d+")


def _fold(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.findall(r"[a-z]+|\d+", plain.replace("-", " "))


# Nombres en toutes lettres, de la forme la plus longue à la plus courte.
_SPELLED = sorted(
    ((tuple(_fold(spell_french_number(n))), n) for n in range(1001)),
    key=lambda item: len(item[0]),
    reverse=True,
)


def expected_numbers(source: str) -> Counter[int]:
    return Counter(int(digits) for digits in _DIGITS.findall(source))


def heard_numbers(transcript: str) -> Counter[int]:
    tokens, heard, position = _fold(transcript), Counter[int](), 0
    while position < len(tokens):
        if tokens[position].isdigit():
            heard[int(tokens[position])] += 1
            position += 1
            continue
        for words, value in _SPELLED:
            if tuple(tokens[position : position + len(words)]) == words:
                heard[value] += 1
                position += len(words)
                break
        else:
            position += 1
    return heard


def main(run_dir: Path) -> None:
    rows = list(csv.DictReader((run_dir / "stt" / "transcriptions.csv").open(encoding="utf-8")))
    sources = {row["id"]: row["texte_envoye"] for row in rows if row["condition"] == "brut"}
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    details = []
    for row in rows:
        condition, source = row["condition"], sources[row["id"]]
        expected, heard = expected_numbers(source), heard_numbers(row["transcription"])
        found = sum(min(count, heard[value]) for value, count in expected.items())
        checks = check_math_audio(source, row["transcription"])
        formula_expected = sum(check.expected for check in checks)
        formula_heard = sum(check.heard for check in checks)
        totals[condition].update(
            numbers_expected=sum(expected.values()),
            numbers_found=found,
            formula_expected=formula_expected,
            formula_heard=formula_heard,
            sentences_with_numbers=bool(expected),
            sentences_all_numbers=bool(expected) and found == sum(expected.values()),
        )
        details.append(
            (row["id"], condition, sum(expected.values()), found, formula_expected, formula_heard)
        )

    output = run_dir / "analyse_complementaire"
    output.mkdir(exist_ok=True)
    with (output / "par_phrase.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(
            (
                "id",
                "condition",
                "nombres_attendus",
                "nombres_retrouves",
                "elements_formule_attendus",
                "elements_formule_retrouves",
            )
        )
        writer.writerows(details)

    def ratio(found: int, expected: int) -> str:
        return f"{found}/{expected} ({100 * found / expected:.1f} %)".replace(".", ",")

    lines = [
        "# Analyse complémentaire : référence commune",
        "",
        "Calculée par `tools/analyse_complementaire.py` à partir de `stt/transcriptions.csv`.",
        "Référence identique pour les trois conditions : la phrase d'origine.",
        "",
        "| Mesure | " + " | ".join(LABELS[c] for c in CONDITIONS) + " |",
        "| --- | ---: | ---: | ---: |",
        "| Nombres de l'énoncé retrouvés | "
        + " | ".join(
            ratio(totals[c]["numbers_found"], totals[c]["numbers_expected"]) for c in CONDITIONS
        )
        + " |",
        "| Phrases dont tous les nombres sont retrouvés | "
        + " | ".join(
            ratio(totals[c]["sentences_all_numbers"], totals[c]["sentences_with_numbers"])
            for c in CONDITIONS
        )
        + " |",
        "| Éléments de formule retrouvés | "
        + " | ".join(
            ratio(totals[c]["formula_heard"], totals[c]["formula_expected"]) for c in CONDITIONS
        )
        + " |",
        "",
        "Détail par phrase : `par_phrase.csv`.",
        "",
    ]
    (output / "resume.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/benchmark-100"))
