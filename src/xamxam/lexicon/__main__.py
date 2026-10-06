"""Vérifie un lexique : python -m xamxam.lexicon [chemin.json]"""

import argparse
import sys
from pathlib import Path

from xamxam.config import DEFAULT_LEXICON_PATH
from xamxam.lexicon.check import find_alphabet_issues, format_issues
from xamxam.lexicon.loader import LexiconError, load_lexicon


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m xamxam.lexicon", description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=DEFAULT_LEXICON_PATH)
    args = parser.parse_args()
    try:
        lexicon = load_lexicon(args.path)
    except LexiconError as exc:
        print(exc, file=sys.stderr)
        return 1
    issues = find_alphabet_issues(lexicon)
    print(f"{args.path} : {len(lexicon.terms)} termes, schéma valide.")
    print(format_issues(issues))
    return 1 if issues else 0


sys.exit(main())
