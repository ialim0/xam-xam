"""Caractères acceptés par les voix TTS Kiriku.

Source : configurations des modèles Coqui VITS publiés sur Hugging Face
(mlroot/ww2, checkpoints/{wolof,pulaar}/config.json, champs `characters` et `punctuations`).
Le serveur met le texte en minuscules ; tout autre caractère est ignoré silencieusement.
Les chiffres sont exclus : le serveur ne convertit que 0 à 10, les autres nombres sont perdus.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

_WOLOF_LETTERS = "abcdefghijklmnopqrstuvwxyzàáâãäçèéêëîïñòóôõùûāīŋœﬁﬂ"
_PULAAR_LETTERS = "'abcdefghijklmnopqrstuvwxyzàâçèéêëìñòôùĩŋũƴɓɗ"
_WOLOF_PUNCTUATION = "\n!%'()*,-./:;?@^_[]«»…“—”‘’ "
_PULAAR_PUNCTUATION = '"\n!%()*,-./:;?@^_[]«»…“—”‘’ '

TTS_ALPHABETS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "wo": frozenset(_WOLOF_LETTERS + _WOLOF_PUNCTUATION),
        "ff": frozenset(_PULAAR_LETTERS + _PULAAR_PUNCTUATION),
    }
)


def unsupported_characters(text: str, language: str = "wo") -> list[str]:
    """Caractères de `text` que la voix TTS de `language` ignorerait, triés et sans doublon."""
    try:
        alphabet = TTS_ALPHABETS[language]
    except KeyError:
        raise ValueError(
            f"Pas d'alphabet TTS connu pour « {language} » "
            f"(disponibles : {', '.join(TTS_ALPHABETS)})."
        ) from None
    normalized = unicodedata.normalize("NFC", text).lower()
    return sorted({char for char in normalized if char not in alphabet})
