"""Contrôle du lexique : caractères que le TTS ignorerait."""

from __future__ import annotations

from dataclasses import dataclass

from xamxam.lexicon.schema import Lexicon
from xamxam.tts_alphabet import unsupported_characters


@dataclass(frozen=True)
class AlphabetIssue:
    term: str
    field: str  # "pronunciation", "term" ou "alias"
    text: str
    characters: tuple[str, ...]


def find_alphabet_issues(lexicon: Lexicon, language: str | None = None) -> list[AlphabetIssue]:
    """Liste les graphies et prononciations contenant des caractères hors de l'alphabet TTS."""
    language = language or lexicon.language
    issues = []
    for term in lexicon.terms:
        candidates = [
            ("pronunciation", term.pronunciation),
            ("term", term.term),
            *(("alias", alias) for alias in term.aliases),
        ]
        for field, text in candidates:
            characters = unsupported_characters(text, language)
            if characters:
                issues.append(AlphabetIssue(term.term, field, text, tuple(characters)))
    return issues


def format_issues(issues: list[AlphabetIssue]) -> str:
    if not issues:
        return "Aucun caractère hors de l'alphabet TTS."
    lines = [f"{len(issues)} entrée(s) avec des caractères ignorés par le TTS :"]
    lines += [
        f"- {i.term} [{i.field}] « {i.text} » : {' '.join(repr(c) for c in i.characters)}"
        for i in issues
    ]
    return "\n".join(lines)
