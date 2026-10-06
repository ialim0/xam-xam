"""Découpage d'un texte trop long pour une seule requête TTS."""

from __future__ import annotations

import re

# Du découpage le plus naturel au plus brutal : phrases, propositions, mots.
_SEPARATORS = (
    re.compile(r"(?<=[.!?;:])\s+"),
    re.compile(r"(?<=,)\s+"),
    re.compile(r"\s+"),
)


def split_text(text: str, limit: int, *, level: int = 0) -> list[str]:
    """Découpe `text` en morceaux de `limit` caractères au plus, en coupant de préférence
    entre les phrases, puis après les virgules, puis entre les mots."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    if level >= len(_SEPARATORS):
        # Un « mot » plus long que la limite : coupure franche.
        return [text[i : i + limit] for i in range(0, len(text), limit)]

    chunks: list[str] = []
    current = ""
    for piece in _SEPARATORS[level].split(text):
        for part in split_text(piece, limit, level=level + 1):
            candidate = f"{current} {part}" if current else part
            if len(candidate) <= limit:
                current = candidate
            else:
                chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    return chunks
