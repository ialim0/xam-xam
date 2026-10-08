"""Tests de bout en bout simulés : Meta, Gemini (agent et résolution), Kiriku et TimaLens
remplacés par des doublures, ffmpeg réel (installé dans la CI)."""

import functools
import json
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
    FakeTimaLens,
    RecordingTTS,
    audio_message,
    build_bot,
    button_reply,
    image_message,
    make_solution,
    text_message,
    tool_results,
    webhook_payload,
)
from xamxam.agent import ScriptedAgentModel
from xamxam.agent.model import call, calls, say
from xamxam.agent.prompt import CREATE_VIDEO, OFFER_BUTTONS, SEND_AUDIO, SEND_TEXT, SOLVE
from xamxam.config import Settings
from xamxam.llm import LLMError
from xamxam.llm.mock import ScriptedLLM
from xamxam.media import wav_to_ogg_opus
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import MockTTSProvider, ProviderError, RateLimiter
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
ANSWER = "BC = √52 ≈ 7,21 cm"
SPOKEN = "Données yi : AB = 4 cm, AC = 6 cm. BC² = AB² + AC², kon BC = √52."
BUTTONS = ["🔊 Écouter", "🎬 Vidéo", "✅ Compris"]
# Ce que fait un agent bien élevé devant un exercice : résoudre, expliquer, proposer.
SOLVE_THEN_EXPLAIN = [
    call(SOLVE, question=""),
    calls(
        (SEND_TEXT, {"texte": f"Tontu bi : {ANSWER}"}),
        (OFFER_BUTTONS, {"texte": "Bëgg nga ?", "boutons": BUTTONS}),
    ),
]


@functools.cache
def _voice_note(seconds: float) -> bytes:
    wav = MockTTSProvider(seconds_per_char=1.0).synthesize("x" * int(seconds))
    return wav_to_ogg_opus(wav)


async def _deliver(bot, *messages) -> None:
    for message in extract_messages(WebhookPayload.model_validate(webhook_payload(*messages))):
        await bot.receive(message)
    await bot.drain()


def _student_message(agent: ScriptedAgentModel, run: int = 0) -> str:
    """Dernier message de l'élève tel que l'agent l'a reçu à sa première étape."""
    return agent.received[run][-1]["content"]


# --- Exercice en photo -------------------------------------------------------------------


async def test_photo_is_solved_explained_and_buttons_offered(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution()])
    agent = ScriptedAgentModel(list(SOLVE_THEN_EXPLAIN))
    bot = build_bot(graph, llm, pipeline=pipeline, agent=agent)
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

    assert graph.read_receipts == ["wamid.img"]  # coche bleue + « en train d'écrire »
    assert graph.kinds == ["text", "text", "interactive"]
    assert graph.texts == [MESSAGES.ack, f"Tontu bi : {ANSWER}"]
    assert graph.buttons == [BUTTONS]
    assert all(m["to"] == STUDENT for m in graph.sent)
    # Gemini (résolution) a reçu la photo ; l'agent, seulement un repère textuel.
    [problem] = llm.calls
    assert problem.image == JPEG and problem.image_mime_type == "image/jpeg"
    assert _student_message(agent) == "[photo de l'exercice jointe]"
    [solved] = tool_results(agent, 1)
    assert solved["statut"] == "ok" and solved["verification"] == "verifie"
    assert solved["reponse_finale"] == ANSWER and solved["explication_wo"]


async def test_wrong_result_is_corrected_once(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution(resultat="7,5"), make_solution()])
    agent = ScriptedAgentModel(list(SOLVE_THEN_EXPLAIN))
    bot = build_bot(graph, llm, pipeline=pipeline, agent=agent)

    await _deliver(bot, image_message())

    first, second = llm.calls
    assert second.correction == "Le résultat correct est 2√13 ≈ 7,21."
    assert second.image == first.image
    assert tool_results(agent, 1)[0]["verification"] == "corrige"


async def test_second_failure_withholds_the_result(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    llm = ScriptedLLM([make_solution(resultat="7,5"), make_solution(resultat="8")])
    agent = ScriptedAgentModel([call(SOLVE, question=""), say("Mënuma ko wóoral.")])
    bot = build_bot(graph, llm, pipeline=pipeline, agent=agent)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    # Le résultat faux n'est jamais transmis à l'agent.
    assert tool_results(agent, 1) == [{"statut": "verification_echouee"}]
    assert graph.texts == [MESSAGES.ack, "Mënuma ko wóoral."]
    assert "Vérification échouée après correction" in caplog.text
    assert '"verification": "echec_apres_correction"' in caplog.text


@pytest.mark.parametrize("status", ["image_illisible", "hors_sujet"])
async def test_unusable_photo_is_reported_to_the_agent(
    pipeline: XamXamPipeline, status: str
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    agent = ScriptedAgentModel([call(SOLVE, question=""), say("Yónnee ma beneen nataal.")])
    bot = build_bot(
        graph, ScriptedLLM([make_solution(statut=status)]), pipeline=pipeline, agent=agent
    )

    await _deliver(bot, image_message())

    assert tool_results(agent, 1) == [{"statut": status}]
    assert graph.texts[-1] == "Yónnee ma beneen nataal."


async def test_unverifiable_notion_is_answered_and_logged(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    solution = make_solution(
        notion="autre", calcul={"type": "aucun", "donnees": [], "resultat": ""}
    )
    agent = ScriptedAgentModel(list(SOLVE_THEN_EXPLAIN))
    bot = build_bot(graph, ScriptedLLM([solution]), pipeline=pipeline, agent=agent)

    with caplog.at_level(logging.INFO):
        await _deliver(bot, image_message())

    assert tool_results(agent, 1)[0]["verification"] == "non_verifie"
    assert "Réponse non vérifiée" in caplog.text


# --- Conversation ------------------------------------------------------------------------


async def test_greeting_gets_a_short_text_reply_without_ack(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    llm = ScriptedLLM([])
    agent = ScriptedAgentModel([say("Maa ngi fi ! Yónnee ma sa exercice.")])
    bot = build_bot(graph, llm, pipeline=pipeline, agent=agent)

    await _deliver(bot, text_message("Salaam aleekum"))

    assert graph.texts == ["Maa ngi fi ! Yónnee ma sa exercice."]
    assert llm.calls == []
    assert _student_message(agent) == "Salaam aleekum"
    assert "Audio (note vocale) : disponible" in agent.systems[0]


async def test_written_exercise_is_passed_to_the_solver(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    llm = ScriptedLLM([make_solution()])
    question = "AB mesure 4 cm, AC mesure 6 cm. Calcule BC."
    agent = ScriptedAgentModel([call(SOLVE, question=question), *SOLVE_THEN_EXPLAIN[1:]])
    bot = build_bot(graph, llm, pipeline=pipeline, agent=agent)

    await _deliver(bot, text_message(question))

    assert llm.calls[0].text == question and llm.calls[0].image is None


async def test_memory_carries_the_conversation_and_escalates_to_video(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    tts = RecordingTTS()
    timalens = FakeTimaLens()
    agent = ScriptedAgentModel(
        [
            *SOLVE_THEN_EXPLAIN,
            say(""),
            # « dégguma » : reformulation en audio.
            call(SEND_AUDIO, texte_wolof=SPOKEN),
            say(""),
            # Toujours pas compris : annonce audio, puis vidéo lancée par l'agent.
            calls(
                (SEND_AUDIO, {"texte_wolof": "Xaaral ma tuuti, maa ngi la defar ab vidéo."}),
                (CREATE_VIDEO, {"texte_wolof": SPOKEN, "titre": "Pythagore"}),
            ),
            say(""),
        ]
    )
    bot = build_bot(
        graph,
        ScriptedLLM([make_solution()]),
        pipeline=pipeline,
        tts=tts,
        agent=agent,
        video=timalens.client(),
    )

    await _deliver(bot, image_message("wamid.1"))
    await _deliver(bot, text_message("dégguma", "wamid.2"))
    await _deliver(bot, button_reply("🎬 Vidéo", "wamid.3"))

    # Deuxième tour : l'agent voit l'historique et l'état de l'exercice.
    second_turn = agent.received[3]
    history = json.dumps(second_turn, ensure_ascii=False)
    assert "[exercice résolu]" in history and f"Tontu bi : {ANSWER}" in history
    assert second_turn[-1]["content"] == "dégguma"
    assert "Notes vocales envoyées pour l'exercice en cours : 0." in agent.systems[3]
    assert "Notes vocales envoyées pour l'exercice en cours : 1." in agent.systems[5]
    assert _student_message(agent, 5) == "🎬 Vidéo"  # clic sur le bouton = texte

    assert graph.kinds[-3:] == ["audio", "audio", "video"]
    video = graph.sent[-1]["video"]
    assert video["link"] == "https://cdn.timalens.test/p1.mp4"
    assert video["caption"] == "Vidéo Xam-Xam : Pythagore"
    assert tool_results(agent, 6)[1] == {"statut": "lancee", "delai": "quelques minutes"}
    # La narration est la voix Kiriku du texte de l'agent, passé par Xam-Xam.
    assert len(timalens.uploads) == 1
    assert "ipoteniws" not in tts.texts[-1] and not set("²=√") & set(tts.texts[-1])


async def test_audio_reply_goes_through_xamxam(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    tts = RecordingTTS()
    text = "BC mooy hypoténuse bi. AB² = 4 cm."
    agent = ScriptedAgentModel([call(SEND_AUDIO, texte_wolof=text)])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, tts=tts, agent=agent)

    await _deliver(bot, text_message("Wax ma ko ci kàddu"))

    assert graph.kinds == ["audio"]
    [upload] = graph.uploads
    assert b"OggS" in upload
    [spoken] = tts.texts
    assert "ipoteniws" in spoken and "aa bee au carré égale quatre centimètres" in spoken
    assert not set("²=√") & set(spoken)


async def test_bot_can_self_check_the_generated_formula(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    stt = FakeSTT("bc au carré égale ab au carré plus ac au carré")
    agent = ScriptedAgentModel([call(SEND_AUDIO, texte_wolof="BC² = AB² + AC²")])
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        stt=stt,
        agent=agent,
        settings=BotSettings(grouping_window_seconds=0, audio_self_check=True),
    )
    await _deliver(bot, text_message("audio"))
    assert graph.kinds == ["audio"]
    assert stt.received  # le WAV sortant a été contrôlé


# --- Notes vocales -----------------------------------------------------------------------


async def test_photo_and_voice_note_are_grouped(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg"), "aud-1": (_voice_note(5), "audio/ogg")})
    stt = FakeSTT("BC lan la wara gis ?")
    agent = ScriptedAgentModel(list(SOLVE_THEN_EXPLAIN))
    settings = BotSettings(
        grouping_window_seconds=0.3, text_grouping_seconds=0.1, reply_mode="texte"
    )
    bot = build_bot(
        graph,
        ScriptedLLM([make_solution()]),
        pipeline=pipeline,
        stt=stt,
        agent=agent,
        settings=settings,
    )

    await _deliver(bot, image_message(), audio_message())

    assert graph.texts.count(MESSAGES.ack) == 1  # un seul accusé, un seul tour d'agent
    assert _student_message(agent) == (
        "[photo de l'exercice jointe]\n[note vocale] BC lan la wara gis ?"
    )
    [audio] = stt.received  # moins de 60 s : envoyée telle quelle (OGG accepté)
    assert audio.startswith(b"OggS")


async def test_long_voice_note_is_split_into_60_second_chunks(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"aud-1": (_voice_note(70), "audio/ogg")})
    stt = FakeSTT("waxtu")
    agent = ScriptedAgentModel([say("Waaw.")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, stt=stt, agent=agent)

    await _deliver(bot, audio_message())

    assert [audio[:4] for audio in stt.received] == [b"RIFF", b"RIFF"]
    assert _student_message(agent) == "[note vocale] waxtu waxtu"


async def test_voice_note_over_120_seconds_is_refused(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"aud-1": (_voice_note(125), "audio/ogg")})
    stt = FakeSTT()
    agent = ScriptedAgentModel([])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, stt=stt, agent=agent)

    await _deliver(bot, audio_message())

    assert graph.texts == [MESSAGES.ack, MESSAGES.audio_too_long]
    assert stt.received == [] and agent.received == []


async def test_long_queue_warns_the_student(pipeline: XamXamPipeline) -> None:
    limiter = RateLimiter(30)
    for _ in range(20):  # 20 requêtes déjà en file : 40 s d'attente
        limiter.reserve()
    graph = FakeGraph(media={"aud-1": (_voice_note(3), "audio/ogg")})
    agent = ScriptedAgentModel([say("Waaw.")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, limiter=limiter, agent=agent)

    await _deliver(bot, audio_message())

    assert graph.texts[:2] == [MESSAGES.ack, MESSAGES.wait_notice]


# --- Sans Kiriku -------------------------------------------------------------------------


async def test_without_kiriku_audio_is_announced_and_voice_tool_unavailable(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph(media={"aud-1": (b"OggS", "audio/ogg")})
    agent = ScriptedAgentModel(
        [call(SEND_AUDIO, texte_wolof="Salaam"), say("Bindal sa laaj, su la neexee.")]
    )
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, voice=False, agent=agent)

    await _deliver(bot, audio_message())

    assert not bot.voice_enabled
    assert "transcription est indisponible" in _student_message(agent)
    assert "Audio (note vocale) : indisponible" in agent.systems[0]
    assert tool_results(agent, 1) == [{"statut": "indisponible"}]
    assert graph.kinds == ["text", "text"] and graph.uploads == []


# --- Vidéo -------------------------------------------------------------------------------


async def test_video_without_kiriku_uses_a_timalens_voice(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    timalens = FakeTimaLens()
    agent = ScriptedAgentModel([call(CREATE_VIDEO, texte_wolof=SPOKEN, titre="Pythagore")])
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        voice=False,
        agent=agent,
        video=timalens.client(),
    )

    await _deliver(bot, text_message("vidéo"))

    assert graph.kinds == ["video"]
    assert "POST /assets/custom-audio" not in timalens.paths
    project = timalens.requests[0][2]
    assert project["source_text"] == SPOKEN
    assert (project["source_mode"], project["language"]) == ("verbatim", "wo")
    assert project["voice_preset"] == "soynade_wo_female"
    assert timalens.requests[-3][2] == {"quote_token": "QT"}


async def test_video_quota_and_single_video_in_progress(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    video = (CREATE_VIDEO, {"texte_wolof": SPOKEN, "titre": "Thalès"})
    agent = ScriptedAgentModel([calls(video, video), say("ok"), calls(video), say("ok")])
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        agent=agent,
        video=FakeTimaLens().client(),
        settings=BotSettings(grouping_window_seconds=0, videos_per_day=1, reply_mode="texte"),
    )

    await _deliver(bot, text_message("vidéo", "wamid.1"))
    await _deliver(bot, text_message("encore", "wamid.2"))

    assert tool_results(agent, 1) == [
        {"statut": "lancee", "delai": "quelques minutes"},
        {"statut": "refusee", "raison": "une vidéo est déjà en préparation"},
    ]
    assert tool_results(agent, 3) == [
        {"statut": "refusee", "raison": "quota de vidéos du jour atteint"}
    ]
    assert "0 restante(s)" in agent.systems[2]
    assert graph.kinds.count("video") == 1


async def test_failed_video_is_reported(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    timalens = FakeTimaLens(states=["generating", "failed"])
    agent = ScriptedAgentModel([call(CREATE_VIDEO, texte_wolof=SPOKEN, titre="x"), say("ok")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=agent, video=timalens.client())

    await _deliver(bot, text_message("vidéo"))

    assert graph.texts[-1] == MESSAGES.video_failed
    assert "POST /projects/p1/confirm" not in timalens.paths


# --- Robustesse --------------------------------------------------------------------------


async def test_agent_failure_and_silence_fall_back_to_error_message(
    pipeline: XamXamPipeline, caplog: pytest.LogCaptureFixture
) -> None:
    graph = FakeGraph()
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        agent=ScriptedAgentModel([LLMError("API Gemini : erreur 503.")]),
    )
    with caplog.at_level(logging.INFO):
        await _deliver(bot, text_message("salut", "wamid.1"))
    assert graph.texts == [MESSAGES.error]
    assert '"error": "LLMError"' in caplog.text

    # Un agent qui tourne en rond est arrêté, et l'élève reçoit quand même une réponse.
    graph = FakeGraph()
    looping = ScriptedAgentModel([call("outil_inexistant")] * 10)
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=looping)
    await _deliver(bot, text_message("salut", "wamid.2"))
    assert len(looping.received) == BotSettings().agent_max_steps
    assert tool_results(looping, 1) == [
        {"statut": "erreur", "detail": "outil inconnu : outil_inexistant"}
    ]
    assert graph.texts == [MESSAGES.error]


async def test_written_question_is_bounded(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    agent = ScriptedAgentModel([])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=agent)

    await _deliver(bot, text_message("a" * 2001))

    assert graph.texts == [MESSAGES.text_too_long]
    assert agent.received == []


async def test_duplicate_notifications_are_processed_once(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    agent = ScriptedAgentModel([say("un"), say("deux")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=agent)

    await _deliver(bot, text_message("salut"))
    await _deliver(bot, text_message("salut"))  # même identifiant de message

    assert graph.texts == ["un"]


async def test_completed_notification_is_not_replayed_after_restart(
    pipeline: XamXamPipeline, tmp_path: Path
) -> None:
    state_path = tmp_path / "bot-state.sqlite3"
    first_graph = FakeGraph()
    first = build_bot(
        first_graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        state_path=state_path,
        agent=ScriptedAgentModel([say("un")]),
    )
    await _deliver(first, text_message("salut"))
    await first.aclose()

    second_graph = FakeGraph()
    second_agent = ScriptedAgentModel([say("deux")])
    second = build_bot(
        second_graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        state_path=state_path,
        agent=second_agent,
    )
    await _deliver(second, text_message("salut"))
    await second.aclose()

    assert first_graph.texts == ["un"]
    assert second_graph.sent == [] and second_agent.received == []


async def test_user_limit_and_unlimited_numbers(pipeline: XamXamPipeline) -> None:
    settings = BotSettings(grouping_window_seconds=0, user_requests_per_hour=1, reply_mode="texte")
    graph = FakeGraph()
    agent = ScriptedAgentModel([say("un"), say("deux")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, settings=settings, agent=agent)

    await _deliver(bot, text_message("a", "wamid.1"))
    await _deliver(bot, text_message("b", "wamid.2"))
    assert graph.texts == ["un", MESSAGES.rate_limited]

    graph = FakeGraph()
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        settings=settings,
        agent=ScriptedAgentModel([say("un"), say("deux")]),
        unlimited=frozenset({STUDENT}),
    )
    await _deliver(bot, text_message("a", "wamid.1"))
    await _deliver(bot, text_message("b", "wamid.2"))
    assert graph.texts == ["un", "deux"]


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
    agent = ScriptedAgentModel([*SOLVE_THEN_EXPLAIN, call(SEND_AUDIO, texte_wolof=SPOKEN)])
    bot = build_bot(graph, ScriptedLLM([make_solution()]), pipeline=pipeline, stt=stt, agent=agent)

    with caplog.at_level(logging.DEBUG):
        await _deliver(bot, image_message(), audio_message(), text_message("sama numéro"))

    assert "audio" in graph.kinds
    logs = caplog.text
    for secret in (STUDENT, "Awa", "damay laaj", "sama numéro", "hypoténuse", "√52"):
        assert secret not in logs
    assert '"outcome": "reponse_envoyee"' in logs
    assert '"outil_resoudre_exercice": 1' in logs
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


async def test_translation_mode_protects_lexicon_terms(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    translator = _Translator()
    solution = make_solution(
        explication_wo="", explication_fr="Les données sont AB = 4 cm. BC est l'hypoténuse."
    )
    agent = ScriptedAgentModel(list(SOLVE_THEN_EXPLAIN))
    bot = build_bot(graph, ScriptedLLM([solution]), pipeline=pipeline, agent=agent)
    bot._translator = translator

    await _deliver(bot, image_message())

    assert "hypoténuse" not in translator.received[0] and "⟦T1⟧" in translator.received[0]
    explanation = tool_results(agent, 1)[0]["explication_wo"]
    assert explanation.startswith("Données yi AB = 4 cm") and "hypoténuse" in explanation


async def test_bot_never_writes_a_transcription_to_disk(
    pipeline: XamXamPipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garde-fou de confidentialité : le bot assemblé par la vraie fabrique (celle de la
    production) ne doit écrire aucune transcription sur disque, ni en cache, ni dans la
    mémoire de conversation (gardée en mémoire vive), ni ailleurs."""
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
    agent = ScriptedAgentModel([*SOLVE_THEN_EXPLAIN, call(SEND_AUDIO, texte_wolof=SPOKEN)])
    monkeypatch.setattr(factory, "GeminiAgentModel", lambda **k: agent)
    settings = Settings(
        whatsapp_token="t",
        whatsapp_phone_number_id="1",
        whatsapp_verify_token="v",
        whatsapp_app_secret="s",
        gemini_api_key="g",
        kvicc_tts_url="https://kiriku.test/tts",
        kvicc_stt_url="https://kiriku.test/stt",
        kvicc_api_key="k",
        cache_dir=tmp_path / "cache",
    )
    bot = factory.build_bot(settings, pipeline, BotSettings(grouping_window_seconds=0))
    graph = FakeGraph(
        media={"img-1": (JPEG, "image/jpeg"), "aud-1": (_voice_note(65), "audio/ogg")}
    )
    bot._meta = graph.client()

    await _deliver(bot, image_message(), audio_message())

    assert "audio" in graph.kinds
    assert transcript in json.dumps(agent.received[0], ensure_ascii=False)  # vu par l'agent
    assert len(stt.received) == 2  # la note de 65 s a bien été transcrite (2 morceaux)
    assert written == [], f"transcription écrite sur disque : {written}"
    for path in (tmp_path / "cache").rglob("*"):
        assert not path.is_file() or secret not in path.read_bytes(), path
    assert not (tmp_path / "cache" / "stt").exists()
    assert any((tmp_path / "cache" / "tts").rglob("*.wav"))  # le cache TTS reste actif


async def test_final_comment_is_not_doubled_and_markers_are_removed(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph()
    agent = ScriptedAgentModel(
        [
            call(SEND_TEXT, texte="[note vocale envoyée] Tontu bi : 5 cm"),
            say("Message envoyé ! À toi de jouer."),
        ]
    )
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=agent)

    await _deliver(bot, text_message("BC ?"))

    assert graph.texts == ["Tontu bi : 5 cm"]


# --- Mode audio (par défaut) : l'élève ne reçoit que des notes vocales ----------------------

AUDIO = BotSettings(grouping_window_seconds=0)  # reply_mode="audio" par défaut


class _BrokenTTS(RecordingTTS):
    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        raise ProviderError("Kiriku : erreur 503.")


async def test_audio_mode_answers_only_with_voice_notes(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    tts = RecordingTTS()
    agent = ScriptedAgentModel(
        [
            say("Maa ngi fi ! Yónnee ma sa exercice."),
            call(SOLVE, question=""),
            # Même si le modèle tente d'écrire, le texte est dit à voix haute.
            calls((SEND_AUDIO, {"texte_wolof": SPOKEN}), (SEND_TEXT, {"texte": "Dégg nga ?"})),
        ]
    )
    bot = build_bot(
        graph,
        ScriptedLLM([make_solution()]),
        pipeline=pipeline,
        tts=tts,
        agent=agent,
        settings=AUDIO,
    )

    await _deliver(bot, text_message("Salaam aleekum", "w1"))
    await _deliver(bot, image_message("w2"))

    assert bot.audio_only
    assert set(graph.kinds) == {"audio"} and graph.texts == []
    # Accusé de réception de la photo compris : tout part en note vocale.
    # (le texte lu est passé par Xam-Xam, d'où une ponctuation normalisée)
    assert tts.texts[0].startswith("Maa ngi fi")
    assert tts.texts[1].startswith("Jërëjëf") and tts.texts[-1].startswith("Dégg nga")
    assert agent.tools[0] == [SOLVE, SEND_AUDIO, CREATE_VIDEO]  # ni texte ni boutons
    assert "Tu réponds uniquement par notes vocales" in agent.systems[0]


async def test_audio_mode_escalates_to_video_after_a_reformulation(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph()
    timalens = FakeTimaLens()
    agent = ScriptedAgentModel(
        [
            call(SOLVE, question="AB = 4, AC = 6, BC ?"),
            call(SEND_AUDIO, texte_wolof=SPOKEN),
            say(""),
            call(SEND_AUDIO, texte_wolof="Nanu ko waxaat ci beneen anam."),
            say(""),
            calls(
                (SEND_AUDIO, {"texte_wolof": "Xaaral ma tuuti, maa ngi la defar ab vidéo."}),
                (CREATE_VIDEO, {"texte_wolof": SPOKEN, "titre": "Pythagore"}),
            ),
        ]
    )
    bot = build_bot(
        graph,
        ScriptedLLM([make_solution()]),
        pipeline=pipeline,
        agent=agent,
        settings=AUDIO,
        video=timalens.client(),
    )

    await _deliver(bot, text_message("AB = 4, AC = 6, BC ?", "w1"))
    await _deliver(bot, text_message("dégguma", "w2"))
    await _deliver(bot, text_message("dégguma rekk", "w3"))

    # L'état indique combien de notes vocales l'élève a déjà reçues pour cet exercice.
    assert "Notes vocales envoyées pour l'exercice en cours : 1." in agent.systems[3]
    assert "Notes vocales envoyées pour l'exercice en cours : 2." in agent.systems[5]
    assert graph.kinds == ["audio", "audio", "audio", "video"]


async def test_audio_mode_falls_back_to_text_when_synthesis_fails(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    agent = ScriptedAgentModel([call(SEND_AUDIO, texte_wolof="Tontu bi : 5 cm")])
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        tts=_BrokenTTS(),
        agent=agent,
        settings=AUDIO,
    )

    await _deliver(bot, image_message())

    # L'élève reçoit quand même l'accusé et la réponse, en texte.
    assert graph.texts == [MESSAGES.ack, "Tontu bi : 5 cm"]
    assert tool_results(agent, 1) == [{"statut": "envoye_en_texte"}]


async def test_audio_mode_needs_kiriku(pipeline: XamXamPipeline) -> None:
    graph = FakeGraph()
    agent = ScriptedAgentModel([say("Bindal sa laaj.")])
    bot = build_bot(
        graph, ScriptedLLM([]), pipeline=pipeline, voice=False, agent=agent, settings=AUDIO
    )

    await _deliver(bot, text_message("salut"))

    assert not bot.audio_only  # sans Kiriku, retour automatique au texte
    assert graph.texts == ["Bindal sa laaj."]
    assert SEND_TEXT in agent.tools[0]


# --- Autocollant d'attente « Néggal tuuti » -------------------------------------------------

STICKER = b"RIFF\x00\x00\x00\x00WEBPVP8X autocollant"


async def test_waiting_sticker_is_sent_for_every_message_and_uploaded_once(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")})
    agent = ScriptedAgentModel([say("un"), say("deux")])
    bot = build_bot(graph, ScriptedLLM([]), pipeline=pipeline, agent=agent, waiting_sticker=STICKER)

    await _deliver(bot, text_message("salut", "w1"))
    await _deliver(bot, image_message("w2"))

    # L'autocollant et « Néggal tuuti » partent avant chaque réponse, même en mode texte,
    # et remplacent l'accusé de réception.
    assert graph.kinds == ["sticker", "audio", "text", "sticker", "audio", "text"]
    assert graph.texts == ["un", "deux"]
    assert [m["sticker"]["id"] for m in graph.sent if m["type"] == "sticker"] == [
        "upload-1",
        "upload-1",
    ]
    # Autocollant et note vocale téléversés une seule fois chacun.
    assert [STICKER in upload for upload in graph.uploads] == [True, False]


async def test_expired_sticker_is_uploaded_again_or_replaced_by_the_ack(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph(media={"img-1": (JPEG, "image/jpeg")}, rejected_media={"upload-1"})
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        agent=ScriptedAgentModel([say("ok")]),
        waiting_sticker=STICKER,
    )
    await _deliver(bot, text_message("salut"))
    # Premier identifiant refusé (expiré) : nouveau téléversement, puis envoi réussi.
    assert graph.kinds == ["sticker", "audio", "text"]
    assert graph.sent[0]["sticker"]["id"] == "upload-2"

    graph = FakeGraph(
        media={"img-1": (JPEG, "image/jpeg")}, rejected_media={"upload-1", "upload-2"}
    )
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        agent=ScriptedAgentModel([say("ok")]),
        waiting_sticker=STICKER,
    )
    await _deliver(bot, image_message())
    # Autocollant impossible : l'accusé de réception habituel le remplace, sans note d'attente.
    assert graph.texts == [MESSAGES.ack, "ok"]
    assert "audio" not in graph.kinds


async def test_audio_mode_adds_a_cached_waiting_voice_note_to_the_sticker(
    pipeline: XamXamPipeline,
) -> None:
    graph = FakeGraph()
    tts = RecordingTTS()
    bot = build_bot(
        graph,
        ScriptedLLM([]),
        pipeline=pipeline,
        tts=tts,
        agent=ScriptedAgentModel([say("un"), say("deux")]),
        waiting_sticker=STICKER,
        settings=AUDIO,
    )

    await _deliver(bot, text_message("salut", "w1"))
    await _deliver(bot, text_message("encore", "w2"))

    # Autocollant puis « Néggal tuuti » à chaque message, avant la réponse.
    assert graph.kinds == ["sticker", "audio", "audio", "sticker", "audio", "audio"]
    waiting = [m["audio"]["id"] for m in graph.sent if m["type"] == "audio"][::2]
    assert waiting[0] == waiting[1]  # même média réutilisé
    # Synthétisée une seule fois : seules les deux réponses passent ensuite par la TTS.
    assert sum(text.startswith("Néggal tuuti") for text in tts.texts) == 1
    assert len(tts.texts) == 3


def test_packaged_waiting_sticker_follows_whatsapp_rules() -> None:
    from xamxam.whatsapp.factory import WAITING_STICKER_PATH

    data = WAITING_STICKER_PATH.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert b"ANIM" in data[:64]  # autocollant animé : 500 Ko au plus
    assert len(data) <= 500 * 1024
    # Canevas VP8X : largeur et hauteur moins un, sur 24 bits.
    width = int.from_bytes(data[24:27], "little") + 1
    height = int.from_bytes(data[27:30], "little") + 1
    assert (width, height) == (512, 512)
