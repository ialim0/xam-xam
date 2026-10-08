"""Client TimaLens : transforme l'explication wolof en vidéo tableau blanc narrée (MP4).

Parcours de l'API (https://api.timalens.com/api/v1, jeton `tlak_…` en Bearer) :
1. POST /projects : projet en mode `verbatim`. Avec un audio (POST /assets/custom-audio),
   l'enregistrement devient la narration : sa voix et son rythme, scènes calées sur ses mots ;
   sans audio, le texte est narré mot pour mot par une voix TimaLens ;
2. POST /projects/{id}/generate : aperçu gratuit (dessins + narration) ;
3. GET /jobs/{id} jusqu'à `preview_ready` ;
4. GET /projects/{id}/quote?action=render, puis POST /projects/{id}/confirm : rendu payant ;
5. GET /jobs/{id} jusqu'à `exported`, qui fournit un `download_url` signé.

Sans TIMALENS_API_KEY, build_timalens_client() retourne None et le bot n'envoie pas de vidéo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from xamxam.config import DEFAULT_TIMALENS_VOICE, Settings
from xamxam.errors import XamXamError
from xamxam.metrics import record_request

logger = logging.getLogger(__name__)

TIMALENS_BASE_URL = "https://api.timalens.com/api/v1"
MAX_SOURCE_CHARS = 40_000
# États d'un projet qui ne progresseront plus.
_FAILED_STATES = frozenset({"failed", "cancelled", "refunded"})

VIDEO_DISABLED_MESSAGE = "Génération vidéo désactivée : TIMALENS_API_KEY n'est pas définie."


class TimaLensError(XamXamError):
    """Échec d'un appel TimaLens. `code` reprend error.code de l'API quand il existe."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class TimaLensDisabledError(TimaLensError):
    """La génération vidéo est demandée alors qu'aucune clé n'est configurée."""


class RenderRefusedError(TimaLensError):
    """Rendu non confirmé : crédits insuffisants ou prix au-dessus du plafond."""


@dataclass(frozen=True)
class RenderQuote:
    token: str
    credits: float
    affordable: bool


@dataclass(frozen=True)
class Narration:
    """Audio envoyé à TimaLens, transcrit dès l'envoi."""

    asset_id: str
    # None si TimaLens ne narre pas la langue détectée ou si la détection n'est pas sûre.
    language: str | None = None


@dataclass(frozen=True)
class JobStatus:
    state: str
    progress: int = 0
    download_url: str | None = None


class TimaLensClient:
    """Appels asynchrones à l'API TimaLens."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = TIMALENS_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
        poll_interval: float = 10.0,
        max_wait_seconds: float = 900.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key:
            raise TimaLensDisabledError(VIDEO_DISABLED_MESSAGE)
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._poll_interval = poll_interval
        self._max_wait = max_wait_seconds
        self._sleep = sleep
        self._clock = clock

    def __repr__(self) -> str:
        # Ne jamais afficher la clé.
        return f"TimaLensClient(base_url={self._base_url!r})"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        record_request("timalens")
        try:
            response = await self._http.request(method, f"{self._base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise TimaLensError(f"TimaLens injoignable ({type(exc).__name__}).") from exc
        if response.is_error:
            code = ""
            with contextlib.suppress(ValueError, AttributeError):
                code = str(response.json().get("error", {}).get("code", ""))
            # Le message d'erreur peut citer le script : seuls le statut et le code sont gardés.
            raise TimaLensError(
                f"TimaLens : erreur {response.status_code} {code}".strip(),
                code=code,
                status=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise TimaLensError("TimaLens : réponse illisible.") from exc
        return data if isinstance(data, dict) else {}

    # --- Étapes de l'API -------------------------------------------------------------

    async def upload_narration(self, audio: bytes, *, mime_type: str, filename: str) -> Narration:
        """Envoie l'enregistrement qui servira de narration (50 Mo au plus)."""
        data = await self._request(
            "POST", "/assets/custom-audio", files={"file": (filename, audio, mime_type)}
        )
        asset_id = data.get("asset_id")
        if not asset_id:
            raise TimaLensError("TimaLens : identifiant de l'audio absent.")
        return Narration(str(asset_id), data.get("language") or None)

    async def create_project(
        self,
        script: str,
        *,
        title: str,
        language: str = "wo",
        voice: str = DEFAULT_TIMALENS_VOICE,
        visual_direction: str | None = None,
        narration: Narration | None = None,
    ) -> str:
        """Crée un projet narrant `script` mot pour mot (ou l'audio `narration`) et retourne
        son identifiant."""
        script = script.strip()
        if not script:
            raise ValueError("Le script de la vidéo est vide.")
        title = title[:200] or "Xam-Xam"
        body: dict[str, Any] = {
            "title": title,
            "source_text": script[:MAX_SOURCE_CHARS],
            "source_mode": "verbatim",
            "language": language,
            "voice_preset": voice,
            # Format vertical : la vidéo est regardée sur téléphone.
            "aspect_ratio": "9:16",
            "visual_engine": "diagram",
        }
        if narration is not None:
            # TimaLens remplace source_text par la transcription de l'audio ; le titre en tête
            # lui permet de reprendre le titre. La voix est celle de l'enregistrement.
            del body["voice_preset"]
            body["source_text"] = f"{title}\n\n{script}"[:MAX_SOURCE_CHARS]
            body["custom_audio_asset_id"] = narration.asset_id
            # La langue n'est pas détectée à la création : celle de l'envoi, sinon la nôtre.
            body["language"] = narration.language or language
        if visual_direction:
            body["visual_direction"] = visual_direction
        project = await self._request("POST", "/projects", json=body)
        project_id = project.get("id")
        if not project_id:
            raise TimaLensError("TimaLens : identifiant du projet absent.")
        return str(project_id)

    async def generate_preview(self, project_id: str) -> None:
        """Lance l'aperçu (gratuit)."""
        await self._request("POST", f"/projects/{project_id}/generate")

    async def job_status(self, project_id: str) -> JobStatus:
        data = await self._request("GET", f"/jobs/{project_id}")
        return JobStatus(
            state=str(data.get("state", "")),
            progress=int(data.get("progress") or 0),
            download_url=data.get("download_url"),
        )

    async def wait_for(self, project_id: str, state: str) -> JobStatus:
        """Interroge /jobs jusqu'à l'état voulu ; échoue si le projet échoue ou traîne."""
        deadline = self._clock() + self._max_wait
        while True:
            status = await self.job_status(project_id)
            if status.state == state:
                return status
            if status.state in _FAILED_STATES:
                raise TimaLensError(f"TimaLens : projet terminé à l'état « {status.state} ».")
            if self._clock() >= deadline:
                raise TimaLensError(
                    f"TimaLens : « {state} » non atteint après {self._max_wait:.0f} s "
                    f"(état « {status.state} », {status.progress} %)."
                )
            await self._sleep(self._poll_interval)

    async def render_quote(self, project_id: str) -> RenderQuote:
        data = await self._request(
            "GET", f"/projects/{project_id}/quote", params={"action": "render"}
        )
        token = data.get("quote_token")
        if not token:
            raise TimaLensError("TimaLens : devis sans quote_token.")
        return RenderQuote(
            token=str(token),
            credits=float(data.get("estimated_credits") or 0.0),
            affordable=bool(data.get("affordable")),
        )

    async def confirm_render(self, project_id: str, quote: RenderQuote) -> None:
        """Rendu payant ; le jeton de devis empêche toute double facturation."""
        await self._request(
            "POST", f"/projects/{project_id}/confirm", json={"quote_token": quote.token}
        )

    # --- Parcours complet ------------------------------------------------------------

    async def make_video(
        self,
        script: str,
        *,
        title: str,
        language: str = "wo",
        voice: str = DEFAULT_TIMALENS_VOICE,
        visual_direction: str | None = None,
        max_credits: float | None = None,
        narration_audio: tuple[bytes, str, str] | None = None,
    ) -> str:
        """Crée, génère, rend la vidéo et retourne son lien de téléchargement signé.
        `narration_audio` (contenu, type MIME, nom de fichier) devient la narration."""
        narration = None
        if narration_audio is not None:
            audio, mime_type, filename = narration_audio
            narration = await self.upload_narration(audio, mime_type=mime_type, filename=filename)
        project_id = await self.create_project(
            script,
            title=title,
            language=language,
            voice=voice,
            visual_direction=visual_direction,
            narration=narration,
        )
        await self.generate_preview(project_id)
        await self.wait_for(project_id, "preview_ready")
        quote = await self.render_quote(project_id)
        if not quote.affordable:
            raise RenderRefusedError(
                f"Crédits TimaLens insuffisants ({quote.credits:g} nécessaires).",
                code="insufficient_credits",
            )
        if max_credits is not None and quote.credits > max_credits:
            raise RenderRefusedError(
                f"Rendu à {quote.credits:g} crédits, au-dessus de TIMALENS_MAX_CREDITS "
                f"({max_credits:g}).",
                code="above_max_credits",
            )
        await self.confirm_render(project_id, quote)
        status = await self.wait_for(project_id, "exported")
        if not status.download_url:
            raise TimaLensError("TimaLens : vidéo exportée sans lien de téléchargement.")
        logger.info("Vidéo TimaLens prête (%g crédits).", quote.credits)
        return status.download_url


def build_timalens_client(settings: Settings) -> TimaLensClient | None:
    """Retourne un client si la clé est configurée, sinon None (vidéo désactivée)."""
    if not settings.timalens_api_key:
        logger.info(VIDEO_DISABLED_MESSAGE)
        return None
    return TimaLensClient(settings.timalens_api_key)
