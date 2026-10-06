"""Liste blanche des modèles autorisés (fichier versionné modeles_autorises.json).

Le bot refuse de démarrer avec un modèle absent de la liste, sans entrée image, ou appelé
dans une région où il n'est pas proposé.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from xamxam.llm.base import LLMConfigurationError

DEFAULT_ALLOWLIST_PATH = Path(__file__).with_name("modeles_autorises.json")
PROVIDERS = ("bedrock", "selfhosted")


class AllowedModel(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    model_id: str = Field(alias="identifiant", min_length=1)
    provider: str
    license: str = Field(alias="licence")
    license_url: str = Field(alias="licence_url")
    regions: tuple[str, ...]
    supports_vision: bool
    supports_tool_use: bool
    source: str


class Allowlist(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    version: str
    policy: str = Field(alias="politique")
    models: tuple[AllowedModel, ...] = Field(alias="modeles")

    def find(self, provider: str, model_id: str) -> AllowedModel | None:
        return next(
            (m for m in self.models if m.provider == provider and m.model_id == model_id), None
        )

    def require(self, provider: str, model_id: str, *, region: str | None = None) -> AllowedModel:
        """Retourne l'entrée du modèle, ou lève LLMConfigurationError avec un message clair."""
        if provider not in PROVIDERS:
            raise LLMConfigurationError(
                f"LLM_PROVIDER inconnu « {provider} » (attendu : {', '.join(PROVIDERS)})."
            )
        entry = self.find(provider, model_id)
        if entry is None:
            allowed = ", ".join(m.model_id for m in self.models if m.provider == provider)
            raise LLMConfigurationError(
                f"Modèle « {model_id} » absent de la liste blanche pour {provider} "
                f"(autorisés : {allowed}). Voir docs/modeles.md."
            )
        if not entry.supports_vision:
            raise LLMConfigurationError(f"Le modèle « {model_id} » n'accepte pas d'image.")
        if region is not None and region not in entry.regions:
            raise LLMConfigurationError(
                f"Le modèle « {model_id} » n'est pas proposé dans la région {region} "
                f"(régions : {', '.join(entry.regions)})."
            )
        return entry


@cache
def _load(path: Path) -> Allowlist:
    try:
        return Allowlist.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise LLMConfigurationError(f"Liste blanche illisible ({path}) : {exc}") from exc


def load_allowlist(path: str | Path = DEFAULT_ALLOWLIST_PATH) -> Allowlist:
    return _load(Path(path))
