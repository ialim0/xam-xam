"""Protection des termes du lexique pendant la traduction.

Chaque occurrence d'un terme est remplacée par un marqueur unique (⟦T1⟧, ⟦T2⟧…) avant
traduction, puis restaurée après. Si un marqueur manque ou apparaît plusieurs fois, la
traduction est considérée comme échouée : le terme scientifique aurait été perdu ou altéré.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from xamxam.lexicon import LexiconIndex
from xamxam.translate.base import TranslationError, Translator

MARKER_TEMPLATE = "⟦T{}⟧"
_MARKER = re.compile(r"⟦T\d+⟧")


@dataclass(frozen=True)
class ProtectedText:
    text: str
    # Marqueur → terme d'origine, tel qu'écrit dans le texte source.
    markers: dict[str, str]


def protect_terms(text: str, index: LexiconIndex) -> ProtectedText:
    if _MARKER.search(text):
        raise TranslationError("Le texte source contient déjà un marqueur de terme.")
    parts: list[str] = []
    markers: dict[str, str] = {}
    cursor = 0
    for number, match in enumerate(index.find_all(text), start=1):
        marker = MARKER_TEMPLATE.format(number)
        markers[marker] = match.surface
        parts += [text[cursor : match.start], marker]
        cursor = match.end
    parts.append(text[cursor:])
    return ProtectedText("".join(parts), markers)


def restore_terms(translated: str, protected: ProtectedText) -> str:
    """Remplace chaque marqueur par son terme ; exige exactement une occurrence de chacun."""
    counts = {marker: translated.count(marker) for marker in protected.markers}
    missing = sum(1 for count in counts.values() if count == 0)
    duplicated = sum(1 for count in counts.values() if count > 1)
    unknown = len(set(_MARKER.findall(translated)) - set(protected.markers))
    if missing or duplicated or unknown:
        # Comptes seulement : le contenu de la traduction n'est jamais journalisé.
        raise TranslationError(
            f"Marqueurs de termes incorrects : {missing} manquant(s), "
            f"{duplicated} dupliqué(s), {unknown} inconnu(s)."
        )
    for marker, term in protected.markers.items():
        translated = translated.replace(marker, term)
    return translated


def translate_protected(text: str, translator: Translator, index: LexiconIndex) -> str:
    protected = protect_terms(text, index)
    try:
        translated = translator.translate(protected.text, source="fr", target="wo")
    except TranslationError:
        raise
    except Exception as exc:  # un traducteur tiers peut lever n'importe quoi
        raise TranslationError(f"Traducteur en échec ({type(exc).__name__}).") from exc
    return restore_terms(translated, protected)
