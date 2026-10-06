"""Tests de bout en bout simulés : Meta, LLM et Kiriku remplacés par des doublures,
ffmpeg réel (installé dans la CI)."""

import functools
import logging
import shutil
import tempfile
from pathlib import Path

import httpx
import pytest

from fakes import (
    STUDENT,
    FakeGraph,
    FakeSTT,
    RecordingTTS,
    audio_message,
    build_bot,
    image_message,
    make_solution,
    text_message,
    webhook_payload,
)
from xamxam.config import Settings
from xamxam.llm.mock import ScriptedLLM
from xamxam.media import wav_to_ogg_opus
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockTTSProvider, RateLimiter
from xamxam.whatsapp import create_app
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.payloads import WebhookPayload, extract_messages
from xamxam.whatsapp.settings import BotSettings
from xamxam.whatsapp.signature import SIGNATURE_HEADER, compute_signature

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg requis"),
]
MESSAGES = BotMessages()
APP_SECRET = "secret-app-test"
JPEG = b"\xff\xd8\xff\xe0 photo d'exercice"


@functools.cache
def _voice_note(seconds: float) -> bytes:
    wav = MockTTSProvider(seconds_per_char=1.0).synthesize("x" * int(seconds))
    return wav_to_ogg_opus(wav)


async def _deliver(bot, *messages) -> None:
    for message in extract_messages(WebhookPayload.model_validate(webhook_payload(*messages))):
        await bot.receive(message)
    await bot.drain()


def _assert_explanation_sent(graph: FakeGraph) -> None:
    assert graph.kinds == ["text", "audio", "text"]
    ack, final = graph.texts
    assert ack == MESSAGES.ack
    assert final == "Tontu bi : BC = √52 ≈ 7,21 cm"
    [upload] = graph.uploads
    assert b"OggS" in upload  # note vocale OGG Opus
    assert all(m["to"] == STUDENT for m in graph.sent)


async def test_photo_in_voice_note_out_through_signed_webhook(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution()])
    tts = RecordingTTS()
    bot = build_bot(graph, llm, pipeline=pipeline, tts=tts)
    settings = Settings(whatsapp_app_secret=APP_SECRET, whatsapp_verify_token="v")
    app = create_app(settings, pipeline=pipeline, tts=MockTTSProvider(), bot=bot)

    body = httpx.Request("POST", "/", json=webhook_payload(image_message())).content
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                SIGNATURE_HEADER: compute_signature(body, APP_SECRET),
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 200
    await bot.drain()

    _assert_explanation_sent(graph)
    [problem] = llm.calls
    assert problem.image == JPEG and problem.image_mime_type == "image/jpeg"
    # L'explication passe par Xam-Xam : symboles convertis en mots, termes réécrits.
    [spoken] = tts.texts
    assert "ipoteniws" in spoken and "teyorem bu Pitagor" in spoken
    assert "A B égale quatre centimètres" in spoken
    assert not set("²=√") & set(spoken)


async def test_photo_and_voice_note_are_grouped(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg"), "aud-1": (_voice_note(5), "audio/ogg")})
    llm = ScriptedLLM([make_solution()])
    stt = FakeSTT("BC lan la wara gis ?")
    settings = BotSettings(grouping_window_seconds=0.3)
    bot = build_bot(graph, llm, pipeline=pipeline, stt=stt, settings=settings)

    await _deliver(bot, image_message(), audio_message())

    _assert_explanation_sent(graph)  # un seul accusé, une seule explication
    [problem] = llm.calls
    assert problem.image == JPEG
    assert problem.transcript == "BC lan la wara gis ?"
    # Une note de moins de 60 s part telle quelle (OGG accepté par le STT Kiriku).
    [audio] = stt.received
    assert audio.startswith(b"OggS")


async def test_long_voice_note_is_split_into_60_second_chunks(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"aud-1": (_voice_note(70), "audio/ogg")})
    stt = FakeSTT("waxtu")
    llm = ScriptedLLM([make_solution()])
    bot = build_bot(graph, llm, pipeline=pipeline, stt=stt)

    await _deliver(bot, audio_message())

    assert [audio[:4] for audio in stt.received] == [b"RIFF", b"RIFF"]
    assert llm.calls[0].transcript == "waxtu waxtu"
    _assert_explanation_sent(graph)


async def test_voice_note_over_120_seconds_is_refused(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"aud-1": (_voice_note(125), "audio/ogg")})
    llm = ScriptedLLM([])
    stt = FakeSTT()
    bot = build_bot(graph, llm, pipeline=pipeline, stt=stt)

    await _deliver(bot, audio_message())

    assert graph.texts == [MESSAGES.ack, MESSAGES.audio_too_long]
    assert stt.received == [] and llm.calls == []


async def test_wrong_result_is_corrected_once(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution(resultat="7,5"), make_solution()])
    bot = build_bot(graph, llm, pipeline=pipeline)

    await _deliver(bot, image_message())

    first, second = llm.calls
    assert second.previous is not None
    assert second.correction == "Le résultat correct est 2√13 ≈ 7,21."
    assert second.image == first.image
    _assert_explanation_sent(graph)


async def test_second_failure_sends_apology_and_is_logged(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution(resultat="7,5"), make_solution(resultat="8")])
    bot = build_bot(graph, llm, pipeline=pipeline)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    assert graph.texts == [MESSAGES.ack, MESSAGES.apology]
    assert graph.uploads == []
    assert "Vérification échouée après correction" in caplog.text
    assert '"outcome": "verification_echouee"' in caplog.text


async def test_unverifiable_notion_is_answered_and_logged(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    solution = make_solution(
        notion="autre",
        calcul={"type": "aucun", "donnees": [], "resultat": ""},
        reponse_finale="BC = √52 ≈ 7,21 cm",
    )
    bot = build_bot(graph, ScriptedLLM([solution]), pipeline=pipeline)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    _assert_explanation_sent(graph)
    assert "Réponse non vérifiée" in caplog.text
    assert '"verification": "non_verifie"' in caplog.text


@pytest.mark.parametrize(
    ("status", "reply"),
    [("image_illisible", MESSAGES.unreadable_image), ("hors_sujet", MESSAGES.off_topic)],
)
async def test_unusable_photo(pipeline: XamXamPipeline, status: str, reply: str) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    bot = build_bot(graph, ScriptedLLM([make_solution(statut=status)]), pipeline=pipeline)

    await _deliver(bot, image_message())

    assert graph.texts == [MESSAGES.ack, reply]


async def test_text_only_gets_help(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    llm = ScriptedLLM([])
    bot = build_bot(graph, llm, pipeline=pipeline)

    await _deliver(bot, text_message("Salaam aleekum"))

    assert graph.texts == [MESSAGES.ack, MESSAGES.help]
    assert llm.calls == []


async def test_duplicate_notifications_are_processed_once(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution()])
    bot = build_bot(graph, llm, pipeline=pipeline)

    await _deliver(bot, image_message())
    await _deliver(bot, image_message())  # même identifiant de message

    assert len(llm.calls) == 1


async def test_user_limit_and_unlimited_numbers(pipeline: XamXamPipeline) -> None:
    settings = BotSettings(grouping_window_seconds=0, user_requests_per_hour=1)
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    bot = build_bot(graph, ScriptedLLM([make_solution()] * 2), pipeline=pipeline, settings=settings)

    await _deliver(bot, image_message("wamid.1"))
    await _deliver(bot, image_message("wamid.2"))
    assert graph.texts[-1] == MESSAGES.rate_limited

    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    bot = build_bot(
        graph,
        ScriptedLLM([make_solution()] * 2),
        pipeline=pipeline,
        settings=settings,
        unlimited=frozenset({STUDENT}),
    )
    await _deliver(bot, image_message("wamid.1"))
    await _deliver(bot, image_message("wamid.2"))
    assert MESSAGES.rate_limited not in graph.texts
    assert len(graph.uploads) == 2


async def test_long_queue_warns_the_student(pipeline: XamXamPipeline) -> None:
    limiter = RateLimiter(30)
    for _ in range(20):  # 20 requêtes déjà en file : 40 s d'attente
        limiter.reserve()
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    bot = build_bot(graph, ScriptedLLM([make_solution()]), pipeline=pipeline, limiter=limiter)

    await _deliver(bot, image_message())

    assert graph.texts[:2] == [MESSAGES.ack, MESSAGES.wait_notice]


async def test_failures_are_reported_without_content(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")}, fail_downloads=True)
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    assert graph.texts == [MESSAGES.ack, MESSAGES.error]
    assert '"error": "MetaError"' in caplog.text


async def test_logs_contain_no_personal_content_and_media_are_deleted(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    before = set(Path(tempfile.gettempdir()).glob("xamxam-*"))
    graph = FakeGraph(
        media={"img-1": (JPEG, "image/jpeg"), "aud-1": (_voice_note(65), "audio/ogg")}
    )
    stt = FakeSTT("sama turu Awa la, damay laaj")
    bot = build_bot(graph, ScriptedLLM([make_solution()]), pipeline=pipeline, stt=stt)

    with caplog.at_level(logging.DEBUG):
        await _deliver(bot, image_message(), audio_message(), text_message("sama numéro"))

    _assert_explanation_sent(graph)
    logs = caplog.text
    for secret in (STUDENT, "Awa", "damay laaj", "sama numéro", "hypoténuse", "√52"):
        assert secret not in logs
    assert '"outcome": "explication_envoyee"' in logs
    assert '"stt": ' in logs or '"durations_ms"' in logs
    assert set(Path(tempfile.gettempdir()).glob("xamxam-*")) == before


class _Translator:
    """Traducteur factice : remplace le français par du « wolof » en gardant les marqueurs."""

    name = "faux"

    def __init__(self, keep_markers: bool = True) -> None:
        self.keep_markers = keep_markers
        self.received: list[str] = []

    def translate(self, text: str, *, source: str = "fr", target: str = "wo") -> str:
        self.received.append(text)
        translated = text.replace("Les données sont", "Données yi").replace("est", "mooy")
        return translated if self.keep_markers else translated.replace("⟦T1⟧", "")


def _french_solution():
    return make_solution(
        explication_wo="",
        explication_fr="Les données sont AB = 4 cm. BC est l'hypoténuse.",
    )


async def test_translation_mode_protects_lexicon_terms(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    tts = RecordingTTS()
    translator = _Translator()
    bot = build_bot(graph, ScriptedLLM([_french_solution()]), pipeline=pipeline, tts=tts)
    bot._translator = translator

    await _deliver(bot, image_message())

    _assert_explanation_sent(graph)
    assert "hypoténuse" not in translator.received[0] and "⟦T1⟧" in translator.received[0]
    [spoken] = tts.texts
    assert spoken.startswith("Données yi A B égale quatre centimètres")
    assert "ipoteniws" in spoken  # terme restauré puis réécrit par le lexique


async def test_failed_translation_sends_apology_and_logs_without_content(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    bot = build_bot(graph, ScriptedLLM([_french_solution()]), pipeline=pipeline)
    bot._translator = _Translator(keep_markers=False)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    assert graph.texts == [MESSAGES.ack, MESSAGES.apology]
    assert "Traduction échouée : Marqueurs de termes incorrects : 1 manquant(s)" in caplog.text
    assert '"outcome": "traduction_echouee"' in caplog.text
    assert "Les données" not in caplog.text and "Données yi" not in caplog.text


async def test_bot_never_writes_a_transcription_to_disk(
    pipeline: XamXamPipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garde-fou de confidentialité : le bot assemblé par la vraie fabrique (celle de la
    production) ne doit écrire aucune transcription sur disque, ni en cache ni ailleurs."""
    import builtins
    import os

    from xamxam.whatsapp import factory

    transcript = "TRANSCRIPTION-SECRETE-6f2a"
    secret = transcript.encode()
    written: list[str] = []

    # Toute écriture de fichier passe par l'un de ces points : on les espionne.
    real_open, real_os_write = builtins.open, os.write
    real_write_bytes, real_write_text = Path.write_bytes, Path.write_text

    def spy_write_bytes(self: Path, data: bytes) -> int:
        if secret in data:
            written.append(str(self))
        return real_write_bytes(self, data)

    def spy_write_text(self: Path, data: str, *args, **kwargs) -> int:
        if transcript in data:
            written.append(str(self))
        return real_write_text(self, data, *args, **kwargs)

    def spy_os_write(fd: int, data: bytes) -> int:
        if secret in bytes(data):
            written.append(f"fd {fd}")
        return real_os_write(fd, data)

    class SpyFile:
        def __init__(self, handle, name: str) -> None:
            self._handle, self._name = handle, name

        def write(self, data):  # type: ignore[no-untyped-def]
            raw = data.encode() if isinstance(data, str) else bytes(data)
            if secret in raw:
                written.append(self._name)
            return self._handle.write(data)

        def __getattr__(self, attribute: str):  # type: ignore[no-untyped-def]
            return getattr(self._handle, attribute)

        def __enter__(self):  # type: ignore[no-untyped-def]
            self._handle.__enter__()
            return self

        def __exit__(self, *exc):  # type: ignore[no-untyped-def]
            return self._handle.__exit__(*exc)

    def spy_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        handle = real_open(file, mode, *args, **kwargs)
        return SpyFile(handle, str(file)) if any(m in mode for m in "wax+") else handle

    monkeypatch.setattr(Path, "write_bytes", spy_write_bytes)
    monkeypatch.setattr(Path, "write_text", spy_write_text)
    monkeypatch.setattr(os, "write", spy_os_write)
    monkeypatch.setattr(builtins, "open", spy_open)

    stt = FakeSTT(transcript)
    monkeypatch.setattr(factory, "create_providers", lambda *a, **k: (MockTTSProvider(), stt))
    monkeypatch.setattr(factory, "create_llm", lambda *a, **k: ScriptedLLM([make_solution()]))
    settings = Settings(
        whatsapp_token="t",
        whatsapp_phone_number_id="1",
        whatsapp_verify_token="v",
        whatsapp_app_secret="s",
        cache_dir=tmp_path / "cache",
    )
    bot = factory.build_bot(settings, pipeline, BotSettings(grouping_window_seconds=0))
    graph = FakeGraph(
        media={"img-1": (JPEG, "image/jpeg"), "aud-1": (_voice_note(65), "audio/ogg")}
    )
    bot._meta = graph.client()

    await _deliver(bot, image_message(), audio_message())

    _assert_explanation_sent(graph)
    assert len(stt.received) == 2  # la note de 65 s a bien été transcrite (2 morceaux)
    assert written == [], f"transcription écrite sur disque : {written}"
    for path in (tmp_path / "cache").rglob("*"):
        assert not path.is_file() or secret not in path.read_bytes(), path
    assert not (tmp_path / "cache" / "stt").exists()
    assert any((tmp_path / "cache" / "tts").rglob("*.wav"))  # le cache TTS reste actif
