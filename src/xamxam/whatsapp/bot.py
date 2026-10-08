"""Orchestration du bot : un agent tuteur conversationnel sur WhatsApp.

Flux d'un message (ou d'un groupe de messages rapprochés) :
1. coche bleue et « en train d'écrire », accusé de réception pour une photo ou un audio ;
2. attente courte pour regrouper photo, note vocale et texte ;
3. téléchargement des médias dans un dossier temporaire supprimé à la fin, transcription
   des notes vocales par Kiriku (découpées par 60 s, 120 s au plus) ;
4. boucle d'agent (Gemini + outils) : il répond en texte, résout l'exercice (Gemini lit la
   photo, SymPy vérifie Pythagore et Thalès), envoie une note vocale, propose des boutons,
   ou lance de lui-même une vidéo TimaLens quand l'élève ne comprend pas.

Mémoire : derniers échanges en texte, en mémoire vive, oubliés après une heure d'inactivité ;
aucune photo ni aucun audio d'élève n'est conservé. Les logs ne contiennent que des
identifiants hachés et des métriques.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from xamxam.agent import (
    AgentModel,
    AgentState,
    Conversation,
    ConversationMemory,
    build_agent_prompt,
    history_messages,
    run_agent,
)
from xamxam.agent.memory import STUDENT, TUTOR
from xamxam.agent.prompt import (
    CREATE_VIDEO,
    OFFER_BUTTONS,
    SEND_AUDIO,
    SEND_TEXT,
    SOLVE,
    tool_declarations,
)
from xamxam.audio_feedback import synthesize_checked
from xamxam.errors import XamXamError
from xamxam.llm import LLMProvider, MathSolution, ProblemInput, SolutionStatus
from xamxam.media import audio_duration, split_audio, wav_to_ogg_opus
from xamxam.metrics import JobMetrics, timed, tracking
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import RateLimiter, STTProvider, TTSProvider
from xamxam.providers.kvicc import MAX_TTS_CHARS
from xamxam.timalens import TimaLensClient
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
_MAX_TEXT_CHARS = 2000
_DAY_SECONDS = 24 * 3600.0
# Repères de la mémoire (« [note vocale envoyée] »…) : le modèle les imite parfois.
_MEMORY_MARKER = re.compile(
    r"\[(?:exercice résolu|note vocale envoyée|boutons\s*:[^\]]*|vidéo[^\]]*"
    r"|la vidéo a échoué)\]\s*",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Texte destiné à l'élève, sans repères internes."""
    return _MEMORY_MARKER.sub("", text).strip()


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


@dataclass
class _Turn:
    """Un tour de conversation : l'élève, sa photo éventuelle (jamais conservée), l'état."""

    sender: str
    user: str
    conversation: Conversation
    metrics: JobMetrics
    image: bytes | None = None
    image_mime: str | None = None
    replied: bool = False


def truncate_explanation(text: str, max_chars: int) -> str:
    """Coupe à la dernière fin de phrase avant la limite (le prompt la demande déjà)."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    end = max(cut.rfind(mark) for mark in ".!?")
    return cut[: end + 1] if end > 0 else cut


def _summary(solution: MathSolution) -> str:
    return f"{solution.statement} → {solution.final_answer}".strip(" →")


class XamXamBot:
    def __init__(
        self,
        *,
        meta: MetaClient,
        llm: LLMProvider,
        agent: AgentModel,
        stt: STTProvider | None,
        tts: TTSProvider | None,
        pipeline: XamXamPipeline,
        kiriku_limiter: RateLimiter,
        hasher: IdHasher,
        settings: BotSettings | None = None,
        messages: BotMessages | None = None,
        unlimited_numbers: frozenset[str] = frozenset(),
        translator: Translator | None = None,
        state_path: Path | None = None,
        video: TimaLensClient | None = None,
        video_voice: str | None = None,
        video_max_credits: float | None = None,
        waiting_sticker: bytes | None = None,
    ) -> None:
        self._meta = meta
        # Autocollant « Néggal tuuti » envoyé à chaque message pendant le traitement ;
        # téléversé une fois, puis réutilisé par son identifiant de média.
        self._waiting_sticker = waiting_sticker
        self._sticker_media_id: str | None = None
        # Sans Kiriku (stt/tts None), l'agent répond en texte et ne transcrit pas les audios.
        self._llm = llm
        self._agent = agent
        self._stt = stt
        self._tts = tts
        self._pipeline = pipeline
        self._kiriku_limiter = kiriku_limiter
        self._hasher = hasher
        self._settings = settings or BotSettings()
        self._messages = messages or BotMessages()
        # Mode traduction : le modèle explique en français, le traducteur produit le wolof.
        self._translator = translator
        self._video = video
        self._video_options: dict[str, Any] = {"max_credits": video_max_credits}
        if video_voice:
            self._video_options["voice"] = video_voice
        clock = time.time if state_path is not None else time.monotonic
        self._user_limits = UserRateLimiter(
            self._settings.user_requests_per_hour,
            unlimited_numbers=unlimited_numbers,
            clock=clock,
            store_path=state_path,
        )
        self._video_quota = UserRateLimiter(
            self._settings.videos_per_day,
            window_seconds=_DAY_SECONDS,
            unlimited_numbers=unlimited_numbers,
            clock=clock,
            store_path=state_path,
            table="videos",
        )
        self._memory = ConversationMemory(ttl_seconds=self._settings.memory_minutes * 60)
        self._deduplicator = MessageDeduplicator(store_path=state_path, hasher=hasher)
        self._bursts: dict[str, _Burst] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def llm_info(self) -> dict[str, str]:
        """Modèles actifs (affichés par /health)."""
        return {
            "provider": self._llm.name,
            "model": getattr(self._llm, "model", ""),
            "agent": getattr(self._agent, "model", ""),
        }

    @property
    def voice_enabled(self) -> bool:
        return self._tts is not None

    @property
    def audio_only(self) -> bool:
        """Réponses uniquement vocales : demandé par la configuration et Kiriku disponible."""
        return self._settings.reply_mode == "audio" and self._tts is not None

    @property
    def video_enabled(self) -> bool:
        return self._video is not None

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

    async def aclose(self) -> None:
        """Ferme les clients HTTP après la fin des traitements."""
        try:
            await self._meta.aclose()
            if self._video is not None:
                await self._video.aclose()
        finally:
            self._user_limits.close()
            self._video_quota.close()
            self._deduplicator.close()

    async def _handle_burst(self, sender: str, burst: _Burst) -> None:
        user = self._hasher(sender)
        completed = False
        try:
            if not self._user_limits.allow(sender, user):
                logger.info("job %s", json.dumps({"user": user, "outcome": "limite_atteinte"}))
                completed = await self._reply(sender, self._messages.rate_limited)
                return
            first = burst.messages[0]
            await self._typing(first.message_id)
            waiting_shown = await self._send_waiting_sticker(sender)
            if not waiting_shown and first.kind in (MessageKind.IMAGE, MessageKind.AUDIO):
                # Sans autocollant : photo ou audio prennent du temps, l'élève est prévenu.
                await self._reply(sender, self._messages.ack)
            await self._wait_for_burst(burst)
            self._bursts.pop(sender, None)
            completed = await self._process(sender, user, burst.messages)
        finally:
            self._bursts.pop(sender, None)
            ids = [message.message_id for message in burst.messages]
            if completed:
                self._deduplicator.mark_done(ids)
            else:
                self._deduplicator.forget(ids)

    async def _wait_for_burst(self, burst: _Burst) -> None:
        """Attente courte pour du texte, plus longue dès qu'une photo ou un audio arrive."""
        window = self._settings.grouping_window_seconds
        short = min(self._settings.text_grouping_seconds, window)
        await asyncio.sleep(short)
        if any(m.kind in (MessageKind.IMAGE, MessageKind.AUDIO) for m in burst.messages):
            await asyncio.sleep(window - short)

    async def _send_waiting_sticker(self, sender: str) -> bool:
        """Autocollant d'attente ; un identifiant expiré (30 jours chez Meta) est renouvelé."""
        if self._waiting_sticker is None:
            return False
        for attempt in (1, 2):
            try:
                if self._sticker_media_id is None:
                    self._sticker_media_id = await self._meta.upload_media(
                        self._waiting_sticker, "image/webp", "attente.webp"
                    )
                await self._meta.send_sticker(sender, self._sticker_media_id)
                return True
            except XamXamError as exc:
                self._sticker_media_id = None
                if attempt == 2:
                    logger.warning("Autocollant d'attente impossible (%s).", type(exc).__name__)
        return False

    async def _typing(self, message_id: str) -> None:
        try:
            await self._meta.mark_read_and_typing(message_id)
        except XamXamError as exc:  # confort seulement : jamais bloquant
            logger.info("Indicateur de saisie impossible (%s).", type(exc).__name__)

    async def _reply(self, sender: str, text: str, *, spoken: bool = True) -> bool:
        """Message fixe (accusé, erreur, limite) : note vocale en mode audio, texte sinon
        ou si la synthèse échoue. `spoken=False` pour ce qui doit rester écrit (un lien)."""
        if spoken and self.audio_only:
            try:
                await self._send_voice(sender, text)
                return True
            except XamXamError as exc:
                logger.warning(
                    "Message vocal impossible (%s) : envoi en texte.", type(exc).__name__
                )
        try:
            await self._meta.send_text(sender, text)
            return True
        except XamXamError as exc:
            logger.warning("Envoi d'un message impossible (%s).", type(exc).__name__)
            return False

    async def _send_voice(self, sender: str, text: str) -> None:
        ogg = await self._speak(text)
        with timed("envoi"):
            media_id = await self._meta.upload_media(ogg, "audio/ogg", "xamxam.ogg")
            await self._meta.send_audio(sender, media_id)

    # --- Traitement ----------------------------------------------------------------

    async def _process(self, sender: str, user: str, messages: Sequence[IncomingMessage]) -> bool:
        metrics = JobMetrics(user=user)
        metrics.inputs.update(m.kind.value for m in messages)
        with tracking(metrics):
            try:
                with timed("total"):
                    await self._converse(sender, user, messages, metrics)
                metrics.outcome = "reponse_envoyee"
                return True
            except _RejectedError as rejection:
                metrics.outcome = rejection.outcome
                return await self._reply(sender, rejection.reply)
            except Exception as exc:  # une tâche de fond ne doit jamais échouer en silence
                metrics.outcome = "erreur"
                metrics.error = type(exc).__name__
                await self._reply(sender, self._messages.error)
                return False
            finally:
                logger.info("job %s", json.dumps(metrics.as_dict()))

    async def _converse(
        self, sender: str, user: str, messages: Sequence[IncomingMessage], metrics: JobMetrics
    ) -> None:
        images = [m for m in messages if m.kind is MessageKind.IMAGE and m.media_id]
        audios = [m for m in messages if m.kind is MessageKind.AUDIO and m.media_id]
        written = " ".join(m.text.strip() for m in messages if m.text and m.text.strip())
        if len(written) > _MAX_TEXT_CHARS:
            raise _RejectedError("texte_trop_long", self._messages.text_too_long)

        turn = _Turn(sender, user, self._memory.get(user), metrics)
        heard: list[str] = []
        with media_workspace() as workspace:
            if images:
                with timed("telechargement"):
                    media = await self._meta.download_media(images[-1].media_id or "")
                turn.image, turn.image_mime = media.content, media.mime_type
                heard.append("[photo de l'exercice jointe]")
            if audios and self._stt is None:
                heard.append("[note vocale reçue, mais la transcription est indisponible]")
            elif audios:
                heard += await self._transcribe_all(sender, audios, workspace, metrics)
        # Les fichiers audio sont effacés ici ; la photo ne vit que le temps du tour.
        if written:
            heard.append(written)
        if not heard:
            heard.append("[message non pris en charge : autocollant, document ou vidéo]")
        await self._run_agent(turn, "\n".join(heard))

    async def _transcribe_all(
        self,
        sender: str,
        audios: Sequence[IncomingMessage],
        workspace: Path,
        metrics: JobMetrics,
    ) -> list[str]:
        chunks: list[list[Path]] = []
        for index, audio in enumerate(audios):
            with timed("telechargement"):
                media = await self._meta.download_media(audio.media_id or "")
            extension = _AUDIO_EXTENSIONS.get(media.mime_type.split(";")[0], ".ogg")
            path = workspace / f"note_{index}{extension}"
            path.write_bytes(media.content)
            chunks.append(await self._prepare_audio(path, workspace))
        metrics.inputs["morceaux_stt"] = sum(len(c) for c in chunks)
        await self._notify_if_slow(sender, metrics.inputs["morceaux_stt"])
        transcripts = [await self._transcribe(c) for c in chunks]
        return [f"[note vocale] {t}" for t in transcripts if t] or ["[note vocale inaudible]"]

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
        assert self._stt is not None  # appelé seulement avec Kiriku
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
        tts_requests = (
            0
            if self._tts is None
            else math.ceil(
                self._settings.max_explanation_chars * _NORMALIZATION_GROWTH / MAX_TTS_CHARS
            )
        )
        wait = self._kiriku_limiter.estimated_wait(stt_requests + tts_requests)
        if wait > self._settings.wait_notice_threshold_seconds:
            await self._reply(sender, self._messages.wait_notice)

    # --- Agent ---------------------------------------------------------------------

    async def _run_agent(self, turn: _Turn, student_message: str) -> None:
        conversation = turn.conversation
        messages = history_messages(conversation)
        if messages and messages[-1]["role"] == "user":
            # Tour précédent resté sans réponse : on fusionne pour garder l'alternance.
            previous = messages.pop()["content"]
            messages.append({"role": "user", "content": f"{previous}\n{student_message}"})
        else:
            messages.append({"role": "user", "content": student_message})
        conversation.note(STUDENT, student_message)

        state = AgentState(
            voice=self._tts is not None,
            video=self._video is not None,
            videos_left_today=self._video_quota.remaining(turn.sender, turn.user),
            video_in_progress=conversation.video_in_progress,
            audio_count=conversation.audio_count,
            exercise=_summary(conversation.solution) if conversation.solution else None,
            audio_only=self.audio_only,
        )
        system = build_agent_prompt(state, max_chars=self._settings.max_explanation_chars)
        with timed("agent"):
            run = await run_agent(
                self._agent,
                system=system,
                messages=messages,
                toolbox=_TurnToolbox(self, turn),
                max_steps=self._settings.agent_max_steps,
            )
        turn.metrics.inputs["etapes_agent"] = run.steps
        turn.metrics.inputs.update(f"outil_{name}" for name in run.tools)
        if not turn.replied:
            # L'agent n'a rien envoyé (limite d'étapes, réponse vide) : l'élève n'attend pas.
            raise _RejectedError("agent_sans_reponse", self._messages.error)

    # --- Outils de l'agent --------------------------------------------------------------

    async def _tool_solve(self, turn: _Turn, question: str) -> dict[str, Any]:
        question = question.strip()
        if turn.image is None and not question:
            return {"statut": "erreur", "detail": "aucune photo ni énoncé à résoudre"}
        problem = ProblemInput(
            image=turn.image, image_mime_type=turn.image_mime, text=question or None
        )
        solution = await self._solve(problem)
        if solution.status is not SolutionStatus.OK:
            return {"statut": solution.status.value}
        verification = verify_solution(solution)
        turn.metrics.verification = verification.status.value
        if verification.status is VerificationStatus.MISMATCH:
            hint = (
                f"Le résultat correct est {verification.expected}."
                if verification.expected
                else f"Problème détecté : {verification.reason}."
            )
            turn.metrics.inputs["correction_demandee"] = 1
            solution = await self._solve(replace(problem, previous=solution, correction=hint))
            verification = verify_solution(solution)
            if verification.status is VerificationStatus.MISMATCH:
                turn.metrics.verification = "echec_apres_correction"
                logger.warning(
                    "Vérification échouée après correction (notion=%s, calcul=%s, cause=%s).",
                    solution.notion,
                    solution.calculation.kind,
                    verification.reason,
                )
                return {"statut": "verification_echouee"}
            turn.metrics.verification = "corrige"
        elif verification.status is VerificationStatus.UNVERIFIED:
            logger.info("Réponse non vérifiée (notion=%s).", solution.notion)
        explanation = await self._wolof_explanation(solution)
        conversation = turn.conversation
        conversation.solution = solution
        conversation.audio_count = 0  # nouvel exercice
        conversation.note(TUTOR, f"[exercice résolu] {_summary(solution)}")
        return {
            "statut": "ok",
            "verification": turn.metrics.verification,
            "enonce": solution.statement,
            "notion": solution.notion.value,
            "etapes": solution.steps,
            "reponse_finale": solution.final_answer,
            "explication_wo": explanation,
        }

    async def _solve(self, problem: ProblemInput) -> MathSolution:
        with timed("llm"):
            return await asyncio.to_thread(self._llm.solve, problem)

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
            return ""

    async def _tool_send_text(self, turn: _Turn, text: str) -> dict[str, Any]:
        text = _clean(text)
        if not text:
            return {"statut": "erreur", "detail": "texte vide"}
        with timed("envoi"):
            await self._meta.send_text(turn.sender, text)
        turn.replied = True
        turn.conversation.note(TUTOR, text)
        return {"statut": "envoye"}

    async def _speak(self, text: str) -> bytes:
        """Texte wolof → Xam-Xam (formules en mots, lexique) → TTS → OGG Opus."""
        assert self._tts is not None
        prepared = self._pipeline.prepare(text).text
        with timed("tts"):
            if self._settings.audio_self_check and self._stt is not None:
                checked = await asyncio.to_thread(
                    synthesize_checked,
                    text,
                    prepared,
                    tts=self._tts,
                    stt=self._stt,
                    language=self._settings.language,
                )
                wav = checked.audio
            else:
                wav = await asyncio.to_thread(
                    self._tts.synthesize, prepared, language=self._settings.language
                )
        with timed("conversion"):
            return await asyncio.to_thread(wav_to_ogg_opus, wav)

    async def _tool_send_audio(self, turn: _Turn, text: str) -> dict[str, Any]:
        if self._tts is None:
            return {"statut": "indisponible"}
        text = truncate_explanation(_clean(text), self._settings.max_explanation_chars)
        if not text:
            return {"statut": "erreur", "detail": "texte vide"}
        try:
            await self._send_voice(turn.sender, text)
        except XamXamError as exc:
            if not self.audio_only:
                raise
            # Mode audio : l'élève doit quand même recevoir la réponse.
            logger.warning("Note vocale impossible (%s) : envoi en texte.", type(exc).__name__)
            await self._tool_send_text(turn, text)
            return {"statut": "envoye_en_texte"}
        turn.replied = True
        turn.conversation.audio_count += 1
        turn.conversation.note(TUTOR, f"[note vocale envoyée] {text}")
        return {"statut": "envoye"}

    async def _tool_offer_buttons(
        self, turn: _Turn, text: str, buttons: Sequence[object]
    ) -> dict[str, Any]:
        text = _clean(text)
        titles = [str(b).strip()[:20] for b in buttons if str(b).strip()][:3]
        if not text or not titles:
            return {"statut": "erreur", "detail": "texte ou boutons manquants"}
        with timed("envoi"):
            await self._meta.send_buttons(turn.sender, text, titles)
        turn.replied = True
        turn.conversation.note(TUTOR, f"{text} [boutons : {' / '.join(titles)}]")
        return {"statut": "envoye"}

    async def _tool_create_video(self, turn: _Turn, text: str, title: str) -> dict[str, Any]:
        conversation = turn.conversation
        if self._video is None:
            return {"statut": "indisponible"}
        if conversation.video_in_progress:
            return {"statut": "refusee", "raison": "une vidéo est déjà en préparation"}
        text = truncate_explanation(_clean(text), self._settings.max_explanation_chars)
        if not text:
            return {"statut": "erreur", "detail": "texte vide"}
        if not self._video_quota.allow(turn.sender, turn.user):
            return {"statut": "refusee", "raison": "quota de vidéos du jour atteint"}
        title = title.strip() or "Xam-Xam"
        conversation.video_in_progress = True
        turn.replied = True  # la vidéo arrivera : l'élève n'est pas laissé sans réponse
        conversation.note(TUTOR, f"[vidéo en préparation : {title}]")
        self._spawn(self._produce_video(turn, text, title))
        return {"statut": "lancee", "delai": "quelques minutes"}

    async def _produce_video(self, turn: _Turn, text: str, title: str) -> None:
        """Tâche de fond : vidéo TimaLens, envoyée par lien. Avec Kiriku, la même voix que
        les notes vocales sert de narration (audio généré, jamais celui de l'élève)."""
        assert self._video is not None
        conversation, sender = turn.conversation, turn.sender
        solution = conversation.solution
        direction = "Tableau de collège, schéma de géométrie clair et annoté."
        if solution is not None:
            direction += f" Exercice : {solution.statement[:500]} Réponse : {solution.final_answer}"
        start = time.monotonic()
        try:
            narration = None
            if self._tts is not None:
                narration = (await self._speak(text), "audio/ogg", "xamxam.ogg")
            link = await self._video.make_video(
                text,
                title=f"Xam-Xam : {title}"[:200],
                language=self._settings.language,
                visual_direction=direction,
                narration_audio=narration,
                **self._video_options,
            )
        except XamXamError as exc:
            logger.warning("Vidéo TimaLens impossible (%s : %s).", type(exc).__name__, exc)
            await self._reply(sender, self._messages.video_failed)
            conversation.note(TUTOR, "[la vidéo a échoué]")
            return
        finally:
            conversation.video_in_progress = False
        caption = self._messages.video_caption.format(title=title)
        try:
            await self._meta.send_video(sender, link, caption)
        except XamXamError as exc:
            # Vidéo trop lourde pour WhatsApp, par exemple : le lien suffit.
            logger.warning("Envoi de la vidéo impossible (%s) : lien envoyé.", type(exc).__name__)
            await self._reply(sender, self._messages.video_link.format(link=link), spoken=False)
        conversation.videos.append(title)
        conversation.note(TUTOR, f"[vidéo envoyée : {title}]")
        logger.info(
            "video %s",
            json.dumps({"user": turn.user, "duree_s": round(time.monotonic() - start)}),
        )


class _TurnToolbox:
    """Outils de l'agent pour un tour : chaque appel agit pour l'élève de ce tour."""

    def __init__(self, bot: XamXamBot, turn: _Turn) -> None:
        self._bot = bot
        self._turn = turn
        self.declarations = tool_declarations(audio_only=bot.audio_only)

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        bot, turn = self._bot, self._turn

        def text(key: str) -> str:
            value = args.get(key, "")
            return value if isinstance(value, str) else str(value)

        if name == SOLVE:
            return await bot._tool_solve(turn, text("question"))
        if bot.audio_only and name in (SEND_TEXT, OFFER_BUTTONS):
            # Mode audio : un texte demandé malgré tout par le modèle est dit à voix haute.
            return await bot._tool_send_audio(turn, text("texte"))
        if name == SEND_TEXT:
            return await bot._tool_send_text(turn, text("texte"))
        if name == SEND_AUDIO:
            return await bot._tool_send_audio(turn, text("texte_wolof"))
        if name == OFFER_BUTTONS:
            buttons = args.get("boutons")
            return await bot._tool_offer_buttons(
                turn, text("texte"), buttons if isinstance(buttons, list) else []
            )
        if name == CREATE_VIDEO:
            return await bot._tool_create_video(turn, text("texte_wolof"), text("titre"))
        return {"statut": "erreur", "detail": f"outil inconnu : {name}"}

    async def say(self, text: str) -> None:
        """Texte final du modèle : envoyé seulement si rien n'est encore parti pendant ce tour.
        Après un envoi par outil, c'est un commentaire (« Message envoyé ! ») à ne pas doubler."""
        if self._turn.replied:
            logger.info("Texte final de l'agent ignoré : réponse déjà envoyée.")
            return
        if self._bot.audio_only:
            await self._bot._tool_send_audio(self._turn, text)
        else:
            await self._bot._tool_send_text(self._turn, text)
