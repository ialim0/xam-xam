"""Orchestration du bot : de la photo ou de la note vocale à l'explication vocale en wolof.

Flux d'une demande :
1. accusé de réception dès le premier message, puis attente pour regrouper photo et audio ;
2. téléchargement des médias dans un dossier temporaire, supprimé à la fin ;
3. transcription des notes vocales (découpées par 60 s, 120 s au plus) ;
4. résolution par le LLM, vérification sympy (Pythagore, Thalès), une correction au plus ;
5. Xam-Xam (normalisation, lexique), TTS, conversion OGG Opus, envoi de la note vocale
   puis de la réponse finale en texte.
Les logs ne contiennent que des identifiants hachés et des métriques.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from xamxam.errors import XamXamError
from xamxam.llm import LLMProvider, MathSolution, ProblemInput, SolutionStatus
from xamxam.media import audio_duration, split_audio, wav_to_ogg_opus
from xamxam.metrics import JobMetrics, timed, tracking
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import RateLimiter, STTProvider, TTSProvider
from xamxam.providers.kvicc import MAX_TTS_CHARS
from xamxam.translate import TranslationError, Translator, translate_protected
from xamxam.verify import VerificationStatus, verify_solution
from xamxam.whatsapp.limits import MessageDeduplicator, UserRateLimiter
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.meta import MetaClient
from xamxam.whatsapp.payloads import IncomingMessage, MessageKind
from xamxam.whatsapp.privacy import IdHasher, media_workspace
from xamxam.whatsapp.settings import BotSettings

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {"audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}
# Le texte normalisé est plus long que l'explication (nombres écrits en lettres).
_NORMALIZATION_GROWTH = 1.3


class _RejectedError(Exception):
    """Fin anticipée d'un traitement : un message a déjà été choisi pour l'élève."""

    def __init__(self, outcome: str, reply: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome
        self.reply = reply


@dataclass
class _Burst:
    """Messages reçus d'un même élève pendant la fenêtre de regroupement."""

    messages: list[IncomingMessage] = field(default_factory=list)


def truncate_explanation(text: str, max_chars: int) -> str:
    """Coupe à la dernière fin de phrase avant la limite (le prompt la demande déjà)."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    end = max(cut.rfind(mark) for mark in ".!?")
    return cut[: end + 1] if end > 0 else cut


class XamXamBot:
    def __init__(
        self,
        *,
        meta: MetaClient,
        llm: LLMProvider,
        stt: STTProvider,
        tts: TTSProvider,
        pipeline: XamXamPipeline,
        kiriku_limiter: RateLimiter,
        hasher: IdHasher,
        settings: BotSettings | None = None,
        messages: BotMessages | None = None,
        unlimited_numbers: frozenset[str] = frozenset(),
        translator: Translator | None = None,
    ) -> None:
        self._meta = meta
        # Mode traduction : le modèle explique en français, le traducteur produit le wolof.
        self._translator = translator
        self._llm = llm
        self._stt = stt
        self._tts = tts
        self._pipeline = pipeline
        self._kiriku_limiter = kiriku_limiter
        self._hasher = hasher
        self._settings = settings or BotSettings()
        self._messages = messages or BotMessages()
        self._user_limits = UserRateLimiter(
            self._settings.user_requests_per_hour, unlimited_numbers=unlimited_numbers
        )
        self._deduplicator = MessageDeduplicator()
        self._bursts: dict[str, _Burst] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def llm_info(self) -> dict[str, str]:
        """Provider et modèle actifs (affichés par /health)."""
        return {"provider": self._llm.name, "model": getattr(self._llm, "model", "")}

    # --- Réception ---------------------------------------------------------------

    async def receive(self, message: IncomingMessage) -> None:
        """Appelé par le webhook : enregistre le message et rend la main immédiatement."""
        if self._deduplicator.is_duplicate(message.message_id):
            return
        burst = self._bursts.get(message.sender)
        if burst is not None:
            burst.messages.append(message)
            return
        burst = _Burst([message])
        self._bursts[message.sender] = burst
        self._spawn(self._handle_burst(message.sender, burst))

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Attend la fin de tous les traitements en cours (tests, arrêt du serveur)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _handle_burst(self, sender: str, burst: _Burst) -> None:
        user = self._hasher(sender)
        try:
            if not self._user_limits.allow(sender, user):
                logger.info("job %s", json.dumps({"user": user, "outcome": "limite_atteinte"}))
                await self._reply(sender, self._messages.rate_limited)
                return
            # L'accusé part dès le premier message, avant la fenêtre de regroupement.
            await self._reply(sender, self._messages.ack)
            await asyncio.sleep(self._settings.grouping_window_seconds)
        finally:
            self._bursts.pop(sender, None)
        await self._process(sender, user, burst.messages)

    async def _reply(self, sender: str, text: str) -> None:
        try:
            await self._meta.send_text(sender, text)
        except XamXamError as exc:
            logger.warning("Envoi d'un message impossible (%s).", type(exc).__name__)

    # --- Traitement ----------------------------------------------------------------

    async def _process(self, sender: str, user: str, messages: Sequence[IncomingMessage]) -> None:
        metrics = JobMetrics(user=user)
        metrics.inputs.update(m.kind.value for m in messages)
        with tracking(metrics):
            try:
                with timed("total"):
                    await self._solve_and_answer(sender, messages, metrics)
                metrics.outcome = "explication_envoyee"
            except _RejectedError as rejection:
                metrics.outcome = rejection.outcome
                await self._reply(sender, rejection.reply)
            except Exception as exc:  # une tâche de fond ne doit jamais échouer en silence
                metrics.outcome = "erreur"
                metrics.error = type(exc).__name__
                await self._reply(sender, self._messages.error)
            finally:
                logger.info("job %s", json.dumps(metrics.as_dict()))

    async def _solve_and_answer(
        self, sender: str, messages: Sequence[IncomingMessage], metrics: JobMetrics
    ) -> None:
        images = [m for m in messages if m.kind is MessageKind.IMAGE and m.media_id]
        audios = [m for m in messages if m.kind is MessageKind.AUDIO and m.media_id]
        texts = [m.text for m in messages if m.kind is MessageKind.TEXT and m.text]
        if not images and not audios:
            raise _RejectedError("aide", self._messages.help)

        with media_workspace() as workspace:
            image, image_mime = None, None
            if images:
                with timed("telechargement"):
                    media = await self._meta.download_media(images[-1].media_id or "")
                image, image_mime = media.content, media.mime_type

            audio_chunks: list[list[Path]] = []
            for index, audio in enumerate(audios):
                with timed("telechargement"):
                    media = await self._meta.download_media(audio.media_id or "")
                extension = _AUDIO_EXTENSIONS.get(media.mime_type.split(";")[0], ".ogg")
                path = workspace / f"note_{index}{extension}"
                path.write_bytes(media.content)
                audio_chunks.append(await self._prepare_audio(path, workspace))
            metrics.inputs["morceaux_stt"] = sum(len(chunks) for chunks in audio_chunks)

            await self._notify_if_slow(sender, metrics.inputs["morceaux_stt"])
            transcripts = [await self._transcribe(chunks) for chunks in audio_chunks]
            problem = ProblemInput(
                image=image,
                image_mime_type=image_mime,
                transcript=" ".join(t for t in transcripts if t) or None,
                text=" ".join(texts) or None,
            )
            solution = await self._solve_verified(problem, metrics)
        # Le dossier temporaire et les médias sont effacés ici, avant la synthèse.
        await self._send_explanation(sender, solution)

    async def _prepare_audio(self, path: Path, workspace: Path) -> list[Path]:
        """Retourne les morceaux à transcrire : l'audio tel quel (le STT accepte l'OGG Opus)
        s'il dure 60 s au plus, sinon des morceaux de 60 s ; refus au-delà de 120 s."""
        duration = await asyncio.to_thread(audio_duration, path)
        if duration > self._settings.max_audio_seconds:
            raise _RejectedError("audio_trop_long", self._messages.audio_too_long)
        if duration <= self._settings.stt_chunk_seconds:
            return [path]
        return await asyncio.to_thread(
            split_audio,
            path,
            workspace / path.stem,
            chunk_seconds=self._settings.stt_chunk_seconds,
        )

    async def _transcribe(self, chunks: Sequence[Path]) -> str:
        parts = []
        with timed("stt"):
            for chunk in chunks:  # successivement, dans l'ordre de l'audio
                text = await asyncio.to_thread(
                    self._stt.transcribe, chunk.read_bytes(), language=self._settings.language
                )
                parts.append(text.strip())
        return " ".join(part for part in parts if part)

    async def _notify_if_slow(self, sender: str, stt_requests: int) -> None:
        """Prévient l'élève si la file Kiriku annonce plus de 30 s d'attente."""
        tts_requests = math.ceil(
            self._settings.max_explanation_chars * _NORMALIZATION_GROWTH / MAX_TTS_CHARS
        )
        wait = self._kiriku_limiter.estimated_wait(stt_requests + tts_requests)
        if wait > self._settings.wait_notice_threshold_seconds:
            await self._reply(sender, self._messages.wait_notice)

    async def _solve_verified(self, problem: ProblemInput, metrics: JobMetrics) -> MathSolution:
        """Résout, vérifie, et redonne une seule fois au modèle le résultat correct si besoin."""
        solution = await self._solve(problem)
        verification = verify_solution(solution)
        if verification.status is VerificationStatus.MISMATCH:
            hint = (
                f"Le résultat correct est {verification.expected}."
                if verification.expected
                else f"Problème détecté : {verification.reason}."
            )
            metrics.inputs["correction_demandee"] = 1
            solution = await self._solve(replace(problem, previous=solution, correction=hint))
            verification = verify_solution(solution)
            if verification.status is VerificationStatus.MISMATCH:
                metrics.verification = "echec_apres_correction"
                logger.warning(
                    "Vérification échouée après correction (notion=%s, calcul=%s, cause=%s).",
                    solution.notion,
                    solution.calculation.kind,
                    verification.reason,
                )
                raise _RejectedError("verification_echouee", self._messages.apology)
            metrics.verification = "corrige"
        else:
            metrics.verification = verification.status.value
            if verification.status is VerificationStatus.UNVERIFIED:
                logger.info("Réponse non vérifiée (notion=%s).", solution.notion)
        return solution

    async def _solve(self, problem: ProblemInput) -> MathSolution:
        with timed("llm"):
            solution = await asyncio.to_thread(self._llm.solve, problem)
        if solution.status is SolutionStatus.UNREADABLE:
            raise _RejectedError("image_illisible", self._messages.unreadable_image)
        if solution.status is SolutionStatus.OFF_TOPIC:
            raise _RejectedError("hors_sujet", self._messages.off_topic)
        return solution

    async def _wolof_explanation(self, solution: MathSolution) -> str:
        if self._translator is None:
            return solution.explanation_wo
        try:
            with timed("traduction"):
                return await asyncio.to_thread(
                    translate_protected,
                    solution.explanation_fr,
                    self._translator,
                    self._pipeline.index,
                )
        except TranslationError as exc:
            # Message de l'erreur : comptes de marqueurs uniquement, jamais le texte.
            logger.warning("Traduction échouée : %s", exc)
            raise _RejectedError("traduction_echouee", self._messages.apology) from exc

    async def _send_explanation(self, sender: str, solution: MathSolution) -> None:
        explanation = truncate_explanation(
            await self._wolof_explanation(solution), self._settings.max_explanation_chars
        )
        text = self._pipeline.prepare(explanation).text
        with timed("tts"):
            wav = await asyncio.to_thread(
                self._tts.synthesize, text, language=self._settings.language
            )
        with timed("conversion"):
            ogg = await asyncio.to_thread(wav_to_ogg_opus, wav)
        with timed("envoi"):
            media_id = await self._meta.upload_media(ogg, "audio/ogg", "xamxam.ogg")
            await self._meta.send_audio(sender, media_id)
            await self._meta.send_text(
                sender, self._messages.final_answer.format(answer=solution.final_answer)
            )
