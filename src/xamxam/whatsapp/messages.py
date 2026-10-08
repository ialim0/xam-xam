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
    # Les réponses de la conversation sont rédigées par l'agent ; ces textes fixes couvrent
    # les cas traités sans lui (accusé, limites, erreurs, vidéo).
    ack: str = "Jërëjëf ! Jot naa sa laaj bi, maa ngi koy xool. Xaaral ma tuuti."
    # Note vocale envoyée avec l'autocollant d'attente, générée une seule fois.
    waiting_audio: str = "Néggal tuuti, maa ngi koy xool."
    wait_notice: str = (
        "Ñu bari ñoo ngi laaj fi léegi. Sa tontu dina yàgg tuuti : xaaral ma, dinaa la tontu."
    )
    audio_too_long: str = "Sa kàddu gi dafa gudd lool. Yónnee ma kàddu gu gàttee ñaari simili."
    text_too_long: str = "Sa bataaxal dafa gudd lool. Yónnee ma laaj bu gàttee."
    rate_limited: str = "Laaj nga lu bari ci waxtu wii. Jéemaatal ci kanam, ba beneen yoon."
    error: str = "Am na jafe-jafe. Baal ma, jéemaatal ci kanam."
    video_caption: str = "Vidéo Xam-Xam : {title}"
    video_link: str = "Sa vidéo mi ngi : {link}"
    video_failed: str = "Baal ma, mënuma defar vidéo bi léegi. Laajal ma ko ci kanam."

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
