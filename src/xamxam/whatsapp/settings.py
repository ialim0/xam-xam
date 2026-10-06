"""Réglages du bot, avec des valeurs par défaut raisonnables (surchargeables par XAMXAM_*)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from xamxam.errors import XamXamError
from xamxam.normalize import NumberLanguage


@dataclass(frozen=True)
class BotSettings:
    # Attente après le premier message pour regrouper photo et note vocale.
    grouping_window_seconds: float = 8.0
    max_explanation_chars: int = 1000
    user_requests_per_hour: int = 10
    # Au-delà, l'élève est prévenu que la réponse va tarder.
    wait_notice_threshold_seconds: float = 30.0
    kiriku_requests_per_minute: float = 30.0
    # Le STT Kiriku accepte 60 s par requête ; au-delà, l'audio est découpé.
    stt_chunk_seconds: float = 60.0
    max_audio_seconds: float = 120.0
    language: str = "wo"
    number_language: NumberLanguage = NumberLanguage.FRENCH

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BotSettings:
        env = os.environ if env is None else env
        defaults = cls()
        overrides: dict[str, object] = {}
        conversions = {
            "XAMXAM_GROUPING_WINDOW_SECONDS": ("grouping_window_seconds", float),
            "XAMXAM_MAX_EXPLANATION_CHARS": ("max_explanation_chars", int),
            "XAMXAM_USER_REQUESTS_PER_HOUR": ("user_requests_per_hour", int),
            "XAMXAM_NUMBER_LANGUAGE": ("number_language", NumberLanguage),
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
