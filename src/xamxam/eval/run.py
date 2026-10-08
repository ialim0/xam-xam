"""Étapes 1 et 2 : audio des trois conditions, aller-retour STT, contrôle des termes cibles."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from xamxam.eval.align import TargetTerm, align_words, check_target_terms, tokenize, word_error_rate
from xamxam.eval.dataset import Sentence, TextColumn
from xamxam.eval.records import (
    AppliedTerms,
    Condition,
    OutputPaths,
    TermRecord,
    TranscriptionRecord,
    write_terms,
    write_transcriptions,
)
from xamxam.lexicon import VALIDATED_ONLY, LexiconIndex, TermStatus
from xamxam.pipeline import PreparedText, XamXamPipeline
from xamxam.providers import STTProvider, TTSProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    transcriptions: tuple[TranscriptionRecord, ...]
    terms: tuple[TermRecord, ...]
    # Statut de prononciation → termes réécrits par le lexique (condition « lexique »).
    applied: dict[str, AppliedTerms]


def build_target(
    term: str,
    index: LexiconIndex,
    applied_statuses: frozenset[TermStatus] = VALIDATED_ONLY,
) -> TargetTerm:
    """N'accepte une prononciation que si son statut est activé pour ce benchmark."""
    entry = index.lookup(term)
    if entry is None:
        logger.warning("Terme cible absent du lexique : « %s ».", term)
        return TargetTerm(term=term, source_forms=(term,), accepted_forms=(term,))
    accepted = (
        (*entry.forms, entry.pronunciation)
        if entry.is_applicable(applied_statuses)
        else entry.forms
    )
    return TargetTerm(
        term=term,
        source_forms=entry.forms,
        accepted_forms=accepted,
    )


def condition_texts(pipeline: XamXamPipeline, source: str) -> dict[Condition, str]:
    """Texte envoyé au TTS pour chaque condition ; chacune ajoute une couche à la précédente."""
    return _texts(pipeline.prepare(source))


def _texts(prepared: PreparedText) -> dict[Condition, str]:
    return {
        Condition.RAW: prepared.source,
        Condition.NORMALIZED: prepared.normalized,
        Condition.FULL: prepared.text,
    }


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
    applied_occurrences: Counter[str] = Counter()
    applied_terms: dict[str, set[str]] = defaultdict(set)

    for sentence in sentences:
        source = sentence.text(text_column)
        targets = [
            build_target(term, pipeline.index, pipeline.applied_statuses)
            for term in sentence.target_terms
        ]

        prepared = pipeline.prepare(source)
        for replacement in prepared.replacements:
            applied_occurrences[replacement.status] += 1
            applied_terms[replacement.status].add(replacement.term)

        for condition, text in _texts(prepared).items():
            audio = tts.synthesize(text, language=text_column)
            audio_path = paths.audio_file(sentence.id, condition)
            audio_path.write_bytes(audio)
            transcript = stt.transcribe(audio, language=text_column)

            alignment = align_words(tokenize(text), tokenize(transcript))
            transcriptions.append(
                TranscriptionRecord(
                    sentence_id=sentence.id,
                    condition=condition,
                    sent_text=text,
                    transcript=transcript,
                    wer=word_error_rate(alignment),
                    audio_file=audio_path.relative_to(paths.root).as_posix(),
                )
            )
            terms.extend(
                TermRecord(sentence.id, condition, check.term, check.occurrences, check.errors)
                for check in check_target_terms(source, transcript, targets)
            )
        logger.info("Phrase %s traitée.", sentence.id)

    write_transcriptions(paths.transcriptions_csv, transcriptions)
    write_terms(paths.terms_csv, terms)
    applied = {
        str(status): AppliedTerms(applied_occurrences[status], tuple(sorted(applied_terms[status])))
        for status in TermStatus
    }
    return RunResult(tuple(transcriptions), tuple(terms), applied)
