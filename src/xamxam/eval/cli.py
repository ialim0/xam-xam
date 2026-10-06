"""Commande en ligne : `python -m xamxam.eval run` et `python -m xamxam.eval report`."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from xamxam.config import (
    DEFAULT_LEXICON_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SENTENCES_PATH,
    DEFAULT_TTS_CACHE_DIR,
    Settings,
)
from xamxam.errors import XamXamError
from xamxam.eval.dataset import load_sentences
from xamxam.eval.human import write_human_template
from xamxam.eval.records import OutputPaths
from xamxam.eval.report import build_report
from xamxam.eval.run import run_evaluation
from xamxam.normalize import NumberLanguage
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import CachedTTSProvider, ProviderName, create_providers

logger = logging.getLogger("xamxam.eval")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m xamxam.eval", description="Évaluation de Xam-Xam (avant / après)."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run", help="Génère les audios, l'aller-retour STT et la fiche humaine."
    )
    run.add_argument("--sentences", type=Path, default=DEFAULT_SENTENCES_PATH)
    run.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    run.add_argument(
        "--provider",
        type=ProviderName,
        choices=list(ProviderName),
        default=ProviderName.AUTO,
        help="auto : KVICC si configuré, sinon mock.",
    )
    run.add_argument(
        "--text-column", choices=("wo", "fr"), default="wo", help="Colonne lue par le TTS."
    )
    run.add_argument(
        "--reading-language", default="fr", help="Langue de lecture des expressions mathématiques."
    )
    run.add_argument(
        "--number-language",
        type=NumberLanguage,
        choices=list(NumberLanguage),
        default=NumberLanguage.FRENCH,
        help="Langue des nombres écrits en lettres : fr (français) ou wo (wolof).",
    )
    run.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_TTS_CACHE_DIR,
        help="Cache des audios TTS : un texte déjà synthétisé n'est jamais régénéré.",
    )
    run.add_argument("--no-cache", action="store_true", help="Désactive le cache audio.")
    run.add_argument(
        "--overwrite-human",
        action="store_true",
        help="Recrée la fiche d'évaluation humaine même si elle existe (annotations perdues).",
    )

    report = commands.add_parser("report", help="Calcule les métriques et écrit le rapport.")
    report.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def _run(args: argparse.Namespace) -> None:
    paths = OutputPaths(args.output_dir)
    tts, stt = create_providers(args.provider, Settings.from_env())
    cache: CachedTTSProvider | None = None
    if not args.no_cache:
        tts = cache = CachedTTSProvider(tts, args.cache_dir)
    result = run_evaluation(
        load_sentences(args.sentences),
        pipeline=XamXamPipeline.from_lexicon_file(
            args.lexicon,
            reading_language=args.reading_language,
            number_language=args.number_language,
        ),
        tts=tts,
        stt=stt,
        paths=paths,
        text_column=args.text_column,
    )
    write_human_template(result.transcriptions, paths.human_csv, overwrite=args.overwrite_human)
    if cache is not None:
        logger.info(
            "Cache audio (%s) : %d réutilisé(s), %d généré(s).",
            args.cache_dir,
            cache.hits,
            cache.misses,
        )
    logger.info(
        "%d audios générés dans %s. Fiche humaine : %s",
        len(result.transcriptions),
        paths.audio_dir,
        paths.human_csv,
    )


def _report(args: argparse.Namespace) -> None:
    paths = OutputPaths(args.output_dir)
    build_report(paths)
    logger.info("Rapport écrit : %s et %s", paths.ranking_csv, paths.summary_md)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            _run(args)
        else:
            _report(args)
    except XamXamError as exc:
        logger.error("%s", exc)
        return 1
    return 0
