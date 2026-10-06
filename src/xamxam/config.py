"""Configuration lue depuis les variables d'environnement.

Aucune variable n'est obligatoire : sans clé, Xam-Xam utilise le provider mock
et la génération vidéo est désactivée.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Chemins par défaut, relatifs à la racine du dépôt.
DEFAULT_LEXICON_PATH = Path("data/lexicon/xam_xam_lexique_v0.json")
DEFAULT_SENTENCES_PATH = Path("data/eval/phrases_pythagore_thales.csv")
DEFAULT_OUTPUT_DIR = Path("outputs")


def _read(env: Mapping[str, str], name: str) -> str | None:
    """Retourne la valeur nettoyée de la variable, ou None si elle est absente ou vide."""
    value = env.get(name, "").strip()
    return value or None


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
        )

    @property
    def kvicc_tts_configured(self) -> bool:
        return bool(self.kvicc_tts_url and self.kvicc_api_key)

    @property
    def kvicc_stt_configured(self) -> bool:
        return bool(self.kvicc_stt_url and self.kvicc_api_key)
