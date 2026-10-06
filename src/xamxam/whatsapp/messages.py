"""Textes envoyés par le bot, configurables.

Les textes wolof par défaut sont des propositions À FAIRE VALIDER par un locuteur natif.
Pour les remplacer sans toucher au code : fichier JSON (tout ou partie des clés) désigné
par XAMXAM_MESSAGES_PATH.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from pathlib import Path

from xamxam.errors import XamXamError


@dataclass(frozen=True)
class BotMessages:
    ack: str = "Jërëjëf ! Jot naa sa laaj bi, maa ngi koy xool. Xaaral ma tuuti."
    wait_notice: str = (
        "Ñu bari ñoo ngi laaj fi léegi. Sa tontu dina yàgg tuuti : xaaral ma, dinaa la tontu."
    )
    unreadable_image: str = (
        "Mënuma jàng nataal bi bu baax. Yónnee ma beneen nataal bu leer, bu wone exercice bi yépp."
    )
    off_topic: str = (
        "Nataal bi du exercice bu mathématiques. Yónnee ma nataalu exercice bi, "
        "walla nga laaj ma ci kàddu."
    )
    apology: str = (
        "Baal ma, mënuma wóoral tontu bi léegi. Jéemaatal ci kanam, walla laajal sa jàngalekat."
    )
    audio_too_long: str = "Sa kàddu gi dafa gudd lool. Yónnee ma kàddu gu gàttee ñaari simili."
    rate_limited: str = "Laaj nga lu bari ci waxtu wii. Jéemaatal ci kanam, ba beneen yoon."
    help: str = (
        "Asalaa maalekum ! Yónnee ma nataalu exercice bi, walla kàddu (note vocale), "
        "ma leral la ko."
    )
    error: str = "Am na jafe-jafe. Baal ma, jéemaatal ci kanam."
    final_answer: str = "Tontu bi : {answer}"

    @classmethod
    def from_json_file(cls, path: str | Path) -> BotMessages:
        try:
            overrides = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise XamXamError(f"Fichier de messages illisible ({path}) : {exc}") from exc
        known = {f.name for f in fields(cls)}
        unknown = set(overrides) - known
        if unknown:
            raise XamXamError(f"Clés de messages inconnues : {', '.join(sorted(unknown))}")
        return replace(cls(), **overrides)
