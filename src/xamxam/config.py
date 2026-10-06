"""Configuration lue depuis les variables d'environnement.

Aucune variable n'est obligatoire : sans clé, Xam-Xam utilise le provider mock,
la génération vidéo est désactivée et le bot WhatsApp répond 503.
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
# En production, XAMXAM_CACHE_DIR pointe vers un bucket Cloud Storage monté.
DEFAULT_CACHE_DIR = Path(".cache")
DEFAULT_TTS_CACHE_DIR = DEFAULT_CACHE_DIR / "tts"
DEFAULT_GRAPH_API_VERSION = "v23.0"


def _read(env: Mapping[str, str], name: str) -> str | None:
    """Retourne la valeur nettoyée de la variable, ou None si elle est absente ou vide."""
    value = env.get(name, "").strip()
    return value or None


def _flag(raw: str | None) -> bool:
    return (raw or "").lower() in {"1", "true", "yes", "oui", "on"}


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
    # Modèle de langage : « bedrock » (déploiement principal) ou « selfhosted » (vLLM, Ollama).
    llm_provider: str | None = None
    bedrock_model_id: str | None = None
    bedrock_region: str | None = None
    selfhosted_base_url: str | None = None
    selfhosted_model: str | None = None
    selfhosted_api_key: str | None = field(default=None, repr=False)
    # Le modèle explique en français simple, puis un traducteur produit le wolof.
    translate_from_french: bool = False
    log_hash_key: str | None = field(default=None, repr=False)
    # Numéros exemptés de la limite par utilisateur (équipe, démos), chiffres seuls.
    unlimited_numbers: frozenset[str] = field(default=frozenset(), repr=False)
    cache_dir: Path = DEFAULT_CACHE_DIR

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
            llm_provider=(_read(env, "LLM_PROVIDER") or "").lower() or None,
            bedrock_model_id=_read(env, "BEDROCK_MODEL_ID"),
            bedrock_region=_read(env, "BEDROCK_REGION"),
            selfhosted_base_url=_read(env, "SELFHOSTED_BASE_URL"),
            selfhosted_model=_read(env, "SELFHOSTED_MODEL"),
            selfhosted_api_key=_read(env, "SELFHOSTED_API_KEY"),
            translate_from_french=_flag(_read(env, "TRANSLATE_FROM_FRENCH")),
            log_hash_key=_read(env, "LOG_HASH_KEY"),
            unlimited_numbers=_phone_numbers(_read(env, "UNLIMITED_NUMBERS")),
            cache_dir=Path(_read(env, "XAMXAM_CACHE_DIR") or DEFAULT_CACHE_DIR),
        )

    @property
    def kvicc_tts_configured(self) -> bool:
        return bool(self.kvicc_tts_url and self.kvicc_api_key)

    @property
    def kvicc_stt_configured(self) -> bool:
        return bool(self.kvicc_stt_url and self.kvicc_api_key)

    @property
    def llm_model(self) -> str | None:
        """Modèle actif selon LLM_PROVIDER."""
        if self.llm_provider == "bedrock":
            return self.bedrock_model_id
        if self.llm_provider == "selfhosted":
            return self.selfhosted_model
        return None

    def missing_bot_variables(self) -> list[str]:
        """Variables indispensables au bot WhatsApp qui ne sont pas définies (noms seulement)."""
        required = {
            "WHATSAPP_TOKEN": self.whatsapp_token,
            "WHATSAPP_PHONE_NUMBER_ID": self.whatsapp_phone_number_id,
            "WHATSAPP_VERIFY_TOKEN": self.whatsapp_verify_token,
            "WHATSAPP_APP_SECRET": self.whatsapp_app_secret,
            "LLM_PROVIDER": self.llm_provider,
        }
        if self.llm_provider == "bedrock":
            required |= {
                "BEDROCK_MODEL_ID": self.bedrock_model_id,
                "BEDROCK_REGION": self.bedrock_region,
            }
        elif self.llm_provider == "selfhosted":
            required |= {
                "SELFHOSTED_BASE_URL": self.selfhosted_base_url,
                "SELFHOSTED_MODEL": self.selfhosted_model,
            }
        return [name for name, value in required.items() if not value]
