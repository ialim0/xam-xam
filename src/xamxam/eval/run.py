"""Étapes 1 et 2 : audio avant/après Xam-Xam, aller-retour STT, contrôle des termes cibles."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from xamxam.eval.align import TargetTerm, align_words, check_target_terms, tokenize, word_error_rate
from xamxam.eval.dataset import Sentence, TextColumn
from xamxam.eval.records import (
    OutputPaths,
    TermRecord,
    TranscriptionRecord,
    Version,
    write_terms,
    write_transcriptions,
)
from xamxam.lexicon import LexiconIndex
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import STTProvider, TTSProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    transcriptions: tuple[TranscriptionRecord, ...]
    terms: tuple[TermRecord, ...]


def build_target(term: str, index: LexiconIndex) -> TargetTerm:
    """Graphies acceptées pour un terme : celles du lexique s'il y figure, sinon le terme seul."""
    entry = index.lookup(term)
    if entry is None:
        logger.warning("Terme cible absent du lexique : « %s ».", term)
        return TargetTerm(term=term, source_forms=(term,), accepted_forms=(term,))
    return TargetTerm(
        term=term,
        source_forms=entry.forms,
        accepted_forms=(*entry.forms, entry.pronunciation),
    )


def run_evaluation(
    sentences: Sequence[Sentence],
    *,
    pipeline: XamXamPipeline,
    tts: TTSProvider,
    stt: STTProvider,
    paths: OutputPaths,
    text_column: TextColumn = "wo",
) -> RunResult:
    """Génère les audios, les retranscrit et écrit les CSV de résultats STT.

    Le WER compare la transcription au texte réellement envoyé au TTS. Les termes cibles,
    eux, sont cherchés dans la transcription à partir de la phrase source : un terme est
    bien restitué si on retrouve sa graphie, un alias ou sa prononciation du lexique.
    """
    paths.audio_dir.mkdir(parents=True, exist_ok=True)
    transcriptions: list[TranscriptionRecord] = []
    terms: list[TermRecord] = []

    for sentence in sentences:
        source = sentence.text(text_column)
        targets = [build_target(term, pipeline.index) for term in sentence.target_terms]
        texts = {Version.BEFORE: source, Version.AFTER: pipeline.prepare(source).text}

        for version, text in texts.items():
            audio = tts.synthesize(text, language=text_column)
            audio_path = paths.audio_file(sentence.id, version)
            audio_path.write_bytes(audio)
            transcript = stt.transcribe(audio, language=text_column)

            alignment = align_words(tokenize(text), tokenize(transcript))
            transcriptions.append(
                TranscriptionRecord(
                    sentence_id=sentence.id,
                    version=version,
                    sent_text=text,
                    transcript=transcript,
                    wer=word_error_rate(alignment),
                    audio_file=audio_path.relative_to(paths.root).as_posix(),
                )
            )
            terms.extend(
                TermRecord(sentence.id, version, check.term, check.occurrences, check.errors)
                for check in check_target_terms(source, transcript, targets)
            )
        logger.info("Phrase %s traitée.", sentence.id)

    write_transcriptions(paths.transcriptions_csv, transcriptions)
    write_terms(paths.terms_csv, terms)
    return RunResult(tuple(transcriptions), tuple(terms))
