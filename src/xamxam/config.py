"""Configuration lue depuis les variables d'environnement (fichier .env chargé par le shell).

Le bot WhatsApp a besoin de Meta (WhatsApp Cloud) et de GEMINI_API_KEY ; sans eux, il répond
503. Kiriku (voix) et TimaLens (vidéo) sont optionnels : sans clé, le bot répond en texte
et n'envoie pas de vidéo. Les commandes d'évaluation fonctionnent sans clé (provider mock).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Chemins par défaut, relatifs à la racine du dépôt.
DEFAULT_LEXICON_PATH = Path("data/lexicon/xam_xam_lexique_v0.json")
DEFAULT_SENTENCES_PATH = Path("data/eval/phrases_pythagore_thales.csv")
DEFAULT_OUTPUT_DIR = Path("outputs")
# Hors de outputs/ pour survivre au nettoyage des résultats d'évaluation.
DEFAULT_CACHE_DIR = Path(".cache")
DEFAULT_TTS_CACHE_DIR = DEFAULT_CACHE_DIR / "tts"
DEFAULT_GRAPH_API_VERSION = "v23.0"
# Gemini 3.5 Flash : lit les photos, appelle des outils, disponible en gratuit, et le
# meilleur wolof de nos essais du 8 octobre 2026.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
# Repli quand le modèle principal est saturé (erreurs 429/5xx répétées, délai dépassé).
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.6-flash"
# Voix wolof de TimaLens (liste : GET https://api.timalens.com/api/v1/generation/options).
DEFAULT_TIMALENS_VOICE = "soynade_wo_female"


def _read(env: Mapping[str, str], name: str) -> str | None:
    """Retourne la valeur nettoyée de la variable, ou None si elle est absente ou vide."""
    value = env.get(name, "").strip()
    return value or None


def _flag(raw: str | None) -> bool:
    return (raw or "").lower() in {"1", "true", "yes", "oui", "on"}


def _number(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Nombre invalide : « {raw} ».") from exc


def normalize_phone_number(number: str) -> str:
    """Ne garde que les chiffres : « +221 77 123 45 67 » → « 221771234567 » (format wa_id)."""
    return re.sub(r"\D", "", number)


def _phone_numbers(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(n for n in (normalize_phone_number(p) for p in raw.split(",")) if n)


@dataclass(frozen=True)
class Settings:
    """Paramètres d'exécution.

    Les secrets sont exclus du repr pour ne jamais fuiter dans les logs.
    """

    kvicc_tts_url: str | None = None
    kvicc_stt_url: str | None = None
    kvicc_api_key: str | None = field(default=None, repr=False)
    timalens_api_key: str | None = field(default=None, repr=False)
    whatsapp_token: str | None = field(default=None, repr=False)
    whatsapp_phone_number_id: str | None = None
    whatsapp_verify_token: str | None = field(default=None, repr=False)
    whatsapp_app_secret: str | None = field(default=None, repr=False)
    whatsapp_graph_api_version: str = DEFAULT_GRAPH_API_VERSION
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_fallback_model: str = DEFAULT_GEMINI_FALLBACK_MODEL
    timalens_voice: str = DEFAULT_TIMALENS_VOICE
    # Plafond de crédits TimaLens par vidéo : au-delà, le rendu payant n'est pas confirmé.
    timalens_max_credits: float | None = None
    # Le modèle explique en français simple, puis un traducteur produit le wolof.
    translate_from_french: bool = False
    # Route de synthèse manuelle, réservée aux tests locaux et désactivée par défaut.
    enable_dev_routes: bool = False
    log_hash_key: str | None = field(default=None, repr=False)
    # Numéros exemptés de la limite par utilisateur (équipe, démos), chiffres seuls.
    unlimited_numbers: frozenset[str] = field(default=frozenset(), repr=False)
    cache_dir: Path = DEFAULT_CACHE_DIR
    state_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Construit les paramètres depuis l'environnement (os.environ par défaut)."""
        env = os.environ if env is None else env
        return cls(
            kvicc_tts_url=_read(env, "KVICC_TTS_URL"),
            kvicc_stt_url=_read(env, "KVICC_STT_URL"),
            kvicc_api_key=_read(env, "KVICC_API_KEY"),
            timalens_api_key=_read(env, "TIMALENS_API_KEY"),
            whatsapp_token=_read(env, "WHATSAPP_TOKEN"),
            whatsapp_phone_number_id=_read(env, "WHATSAPP_PHONE_NUMBER_ID"),
            whatsapp_verify_token=_read(env, "WHATSAPP_VERIFY_TOKEN"),
            whatsapp_app_secret=_read(env, "WHATSAPP_APP_SECRET"),
            whatsapp_graph_api_version=_read(env, "WHATSAPP_GRAPH_API_VERSION")
            or DEFAULT_GRAPH_API_VERSION,
            gemini_api_key=_read(env, "GEMINI_API_KEY"),
            gemini_model=_read(env, "GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            gemini_fallback_model=_read(env, "GEMINI_FALLBACK_MODEL")
            or DEFAULT_GEMINI_FALLBACK_MODEL,
            timalens_voice=_read(env, "TIMALENS_VOICE") or DEFAULT_TIMALENS_VOICE,
            timalens_max_credits=_number(_read(env, "TIMALENS_MAX_CREDITS")),
            translate_from_french=_flag(_read(env, "TRANSLATE_FROM_FRENCH")),
            enable_dev_routes=_flag(_read(env, "XAMXAM_ENABLE_DEV_ROUTES")),
            log_hash_key=_read(env, "LOG_HASH_KEY"),
            unlimited_numbers=_phone_numbers(_read(env, "UNLIMITED_NUMBERS")),
            cache_dir=Path(_read(env, "XAMXAM_CACHE_DIR") or DEFAULT_CACHE_DIR),
            state_dir=Path(value) if (value := _read(env, "XAMXAM_STATE_DIR")) else None,
        )

    @property
    def kvicc_tts_configured(self) -> bool:
        return bool(self.kvicc_tts_url and self.kvicc_api_key)

    @property
    def kvicc_stt_configured(self) -> bool:
        return bool(self.kvicc_stt_url and self.kvicc_api_key)

    @property
    def video_enabled(self) -> bool:
        return bool(self.timalens_api_key)

    def missing_bot_variables(self) -> list[str]:
        """Variables indispensables au bot WhatsApp qui ne sont pas définies (noms seulement)."""
        required = {
            "WHATSAPP_TOKEN": self.whatsapp_token,
            "WHATSAPP_PHONE_NUMBER_ID": self.whatsapp_phone_number_id,
            "WHATSAPP_VERIFY_TOKEN": self.whatsapp_verify_token,
            "WHATSAPP_APP_SECRET": self.whatsapp_app_secret,
            "GEMINI_API_KEY": self.gemini_api_key,
        }
        return [name for name, value in required.items() if not value]
