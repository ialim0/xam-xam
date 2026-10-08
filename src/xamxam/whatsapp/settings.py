"""Réglages du bot, avec des valeurs par défaut raisonnables (surchargeables par XAMXAM_*)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from xamxam.errors import XamXamError
from xamxam.normalize import NumberLanguage


def _boolean(raw: str) -> bool:
    value = raw.casefold()
    if value in {"1", "true", "yes", "oui", "on"}:
        return True
    if value in {"0", "false", "no", "non", "off"}:
        return False
    raise ValueError(raw)


def _reply_mode(raw: str) -> str:
    value = raw.casefold()
    if value not in {"audio", "texte"}:
        raise ValueError(raw)
    return value


@dataclass(frozen=True)
class BotSettings:
    # Attente après le premier message pour regrouper photo et note vocale.
    grouping_window_seconds: float = 8.0
    # Attente plus courte quand l'élève n'envoie que du texte (conversation).
    text_grouping_seconds: float = 2.0
    max_explanation_chars: int = 1000
    # Un message (ou groupe de messages) compte pour une demande.
    user_requests_per_hour: int = 30
    videos_per_day: int = 5
    # Mémoire de conversation, en mémoire vive uniquement.
    memory_minutes: float = 60.0
    agent_max_steps: int = 6
    # « audio » : l'élève ne reçoit que des notes vocales (texte en secours si la synthèse
    # échoue) ; « texte » : réponses écrites, avec audio et boutons à la demande.
    reply_mode: str = "audio"
    # Autocollant animé envoyé à chaque message pendant le traitement (False : désactivé).
    waiting_sticker: bool = True
    # Au-delà, l'élève est prévenu que la réponse va tarder.
    wait_notice_threshold_seconds: float = 30.0
    kiriku_requests_per_minute: float = 30.0
    # Le STT Kiriku accepte 60 s par requête ; au-delà, l'audio est découpé.
    stt_chunk_seconds: float = 60.0
    max_audio_seconds: float = 120.0
    language: str = "wo"
    number_language: NumberLanguage = NumberLanguage.FRENCH
    # Vérifie les formules de l'audio généré par STT et tente au plus deux variantes.
    audio_self_check: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BotSettings:
        env = os.environ if env is None else env
        defaults = cls()
        overrides: dict[str, object] = {}
        conversions = {
            "XAMXAM_GROUPING_WINDOW_SECONDS": ("grouping_window_seconds", float),
            "XAMXAM_MAX_EXPLANATION_CHARS": ("max_explanation_chars", int),
            "XAMXAM_USER_REQUESTS_PER_HOUR": ("user_requests_per_hour", int),
            "XAMXAM_VIDEOS_PER_DAY": ("videos_per_day", int),
            "XAMXAM_MEMORY_MINUTES": ("memory_minutes", float),
            "XAMXAM_REPLY_MODE": ("reply_mode", _reply_mode),
            "XAMXAM_WAITING_STICKER": ("waiting_sticker", _boolean),
            "XAMXAM_NUMBER_LANGUAGE": ("number_language", NumberLanguage),
            "XAMXAM_AUDIO_SELF_CHECK": ("audio_self_check", _boolean),
        }
        for variable, (attribute, convert) in conversions.items():
            raw = env.get(variable, "").strip()
            if not raw:
                continue
            try:
                overrides[attribute] = convert(raw)
            except ValueError as exc:
                raise XamXamError(f"{variable} invalide : « {raw} ».") from exc
        return cls(**{**defaults.__dict__, **overrides})
