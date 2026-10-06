"""Outils du lexique.

python -m xamxam.lexicon [check] [lexique.json]
python -m xamxam.lexicon convert source.json [destination.json]
python -m xamxam.lexicon export-validation [--sentences …] [--output …]
python -m xamxam.lexicon import-validation [fichier.csv]
"""

import argparse
import sys
from pathlib import Path

from xamxam.config import DEFAULT_LEXICON_PATH, DEFAULT_SENTENCES_PATH
from xamxam.errors import XamXamError
from xamxam.lexicon.check import find_alphabet_issues, format_issues
from xamxam.lexicon.convert import convert_file, lexicon_to_json
from xamxam.lexicon.index import LexiconIndex
from xamxam.lexicon.loader import load_lexicon
from xamxam.lexicon.validation import apply_validations, read_validation_csv, write_validation_csv

DEFAULT_VALIDATION_PATH = Path("data/lexicon/termes_cibles_a_valider.csv")
COMMANDS = ("check", "convert", "export-validation", "import-validation")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m xamxam.lexicon", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Valide le schéma et l'alphabet TTS.")
    check.add_argument("path", type=Path, nargs="?", default=DEFAULT_LEXICON_PATH)

    convert = commands.add_parser("convert", help="Convertit un lexique au schéma source.")
    convert.add_argument("source", type=Path)
    convert.add_argument("destination", type=Path, nargs="?", default=DEFAULT_LEXICON_PATH)

    export = commands.add_parser("export-validation", help="Génère le CSV de validation.")
    export.add_argument("--sentences", type=Path, default=DEFAULT_SENTENCES_PATH)
    export.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)
    export.add_argument("--output", type=Path, default=DEFAULT_VALIDATION_PATH)

    imp = commands.add_parser("import-validation", help="Réimporte le CSV rempli.")
    imp.add_argument("path", type=Path, nargs="?", default=DEFAULT_VALIDATION_PATH)
    imp.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)
    return parser


def _check(path: Path) -> int:
    lexicon = load_lexicon(path)
    issues = find_alphabet_issues(lexicon)
    validated = sum(t.is_validated for t in lexicon.terms)
    without = sum(t.pronunciation is None for t in lexicon.terms)
    print(
        f"{path} : {len(lexicon.terms)} termes, schéma valide "
        f"({validated} validé(s), {len(lexicon.terms) - validated} brouillon(s), "
        f"{without} sans prononciation)."
    )
    print(format_issues(issues))
    return 1 if issues else 0


def _export(args: argparse.Namespace) -> int:
    from xamxam.eval.align import count_occurrences, tokenize
    from xamxam.eval.dataset import load_sentences
    from xamxam.eval.run import build_target

    index = LexiconIndex(load_lexicon(args.lexicon))
    sentences = load_sentences(args.sentences)
    occurrences = {}
    for term in sorted({t for s in sentences for t in s.target_terms}):
        forms = build_target(term, index).source_forms
        occurrences[term] = sum(count_occurrences(tokenize(s.wo), forms) for s in sentences)
    write_validation_csv(args.output, occurrences, index)
    print(f"{len(occurrences)} termes cibles écrits dans {args.output}.")
    return 0


def _import(args: argparse.Namespace) -> int:
    lexicon = load_lexicon(args.lexicon)
    updated, summary = apply_validations(
        lexicon, read_validation_csv(args.path), source=str(args.path)
    )
    args.lexicon.write_text(lexicon_to_json(updated), encoding="utf-8")
    print(
        f"{len(summary.validated)} terme(s) passé(s) au statut valide, "
        f"{summary.ignored} ligne(s) sans prononciation validée ignorée(s)."
    )
    return _check(args.lexicon)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Compatibilité : « python -m xamxam.lexicon [chemin] » équivaut à « check ».
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        argv = ["check", *argv]
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args.path)
        if args.command == "convert":
            lexicon = convert_file(args.source, args.destination)
            print(f"{len(lexicon.terms)} termes convertis dans {args.destination}.")
            return _check(args.destination)
        if args.command == "export-validation":
            return _export(args)
        return _import(args)
    except XamXamError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
