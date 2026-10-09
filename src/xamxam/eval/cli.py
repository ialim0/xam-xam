"""Commande en ligne : `python -m xamxam.eval run`, `report` et `llm`."""

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
from xamxam.eval.blind import create_blind_sheet, import_blind_sheet
from xamxam.eval.dataset import DatasetError, load_sentences
from xamxam.eval.human import write_human_template
from xamxam.eval.records import OutputPaths, RunInfo
from xamxam.eval.report import build_report
from xamxam.eval.run import generate_audio, run_evaluation
from xamxam.lexicon import VALIDATED_AND_DRAFT, VALIDATED_ONLY
from xamxam.normalize import NumberLanguage
from xamxam.pipeline import XamXamPipeline
from xamxam.providers import (
    CachedSTTProvider,
    CachedTTSProvider,
    ProviderName,
    create_providers,
    create_tts_provider,
)

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
        help="Cache TTS (et STT dans le dossier voisin « stt ») de l'évaluation.",
    )
    run.add_argument("--no-cache", action="store_true", help="Désactive les caches TTS et STT.")
    run.add_argument(
        "--lexique-statut",
        choices=("valide", "brouillon"),
        default="valide",
        help="valide : seules les prononciations validées sont appliquées ; "
        "brouillon : les brouillons le sont aussi.",
    )
    run.add_argument(
        "--limit", type=int, default=None, help="Ne traite que les N premières phrases."
    )
    run.add_argument(
        "--overwrite-human",
        action="store_true",
        help="Recrée la fiche d'évaluation humaine même si elle existe (annotations perdues).",
    )

    audio = commands.add_parser(
        "audio", help="Génère les trois WAV par phrase sans appeler le STT."
    )
    audio.add_argument("--sentences", type=Path, default=DEFAULT_SENTENCES_PATH)
    audio.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)
    audio.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    audio.add_argument("--cache-dir", type=Path, default=DEFAULT_TTS_CACHE_DIR)
    audio.add_argument(
        "--provider", type=ProviderName, choices=list(ProviderName), default=ProviderName.AUTO
    )
    audio.add_argument(
        "--number-language",
        type=NumberLanguage,
        choices=list(NumberLanguage),
        default=NumberLanguage.FRENCH,
    )
    audio.add_argument("--lexique-statut", choices=("valide", "brouillon"), default="valide")

    check = commands.add_parser("check", help="Contrôle le jeu de phrases du benchmark.")
    check.add_argument("--sentences", type=Path, default=DEFAULT_SENTENCES_PATH)
    check.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)

    report = commands.add_parser("report", help="Calcule les métriques et écrit le rapport.")
    report.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    blind = commands.add_parser(
        "blind", help="Prépare les audios et la fiche de notation à l'aveugle."
    )
    blind.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    blind.add_argument("--seed", type=int, default=None)
    blind.add_argument("--overwrite-blind", action="store_true")

    unblind = commands.add_parser("unblind", help="Réintègre les notes aveugles au rapport.")
    unblind.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    unblind.add_argument("--overwrite-human", action="store_true")

    llm = commands.add_parser("llm", help="Compare des modèles Gemini sur des photos.")
    llm.add_argument("--photos", type=Path, required=True, help="Dossier des photos d'exercices.")
    llm.add_argument(
        "--verite", type=Path, help="Vérité terrain (défaut : <photos>/verite_terrain.csv)."
    )
    llm.add_argument(
        "--configs", type=Path, required=True, help="Configurations à comparer (JSON)."
    )
    llm.add_argument("--repetitions", type=int, default=3)
    llm.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON_PATH)
    llm.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "llm")
    return parser


def _run(args: argparse.Namespace) -> None:
    paths = OutputPaths(args.output_dir)
    tts, stt = create_providers(args.provider, Settings.from_env())
    cache: CachedTTSProvider | None = None
    if not args.no_cache:
        tts = cache = CachedTTSProvider(tts, args.cache_dir)
        # Évaluation uniquement : les transcriptions des phrases de test sont mises en cache.
        stt = CachedSTTProvider(stt, args.cache_dir.parent / "stt")
    sentences = load_sentences(args.sentences)
    if args.limit is not None:
        if args.limit < 1:
            raise DatasetError("--limit doit valoir au moins 1.")
        sentences = sentences[: args.limit]
    statuses = VALIDATED_AND_DRAFT if args.lexique_statut == "brouillon" else VALIDATED_ONLY
    result = run_evaluation(
        sentences,
        pipeline=XamXamPipeline.from_lexicon_file(
            args.lexicon,
            reading_language=args.reading_language,
            number_language=args.number_language,
            applied_statuses=statuses,
        ),
        tts=tts,
        stt=stt,
        paths=paths,
        text_column=args.text_column,
    )
    RunInfo(
        sentences=len(sentences),
        number_language=str(args.number_language),
        lexicon_status=args.lexique_statut,
        applied=result.applied,
    ).write(paths.run_info_json)
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


def _audio(args: argparse.Namespace) -> None:
    paths = OutputPaths(args.output_dir)
    tts = CachedTTSProvider(create_tts_provider(args.provider, Settings.from_env()), args.cache_dir)
    sentences = load_sentences(args.sentences)
    statuses = VALIDATED_AND_DRAFT if args.lexique_statut == "brouillon" else VALIDATED_ONLY
    result = generate_audio(
        sentences,
        pipeline=XamXamPipeline.from_lexicon_file(
            args.lexicon, number_language=args.number_language, applied_statuses=statuses
        ),
        tts=tts,
        paths=paths,
    )
    RunInfo(
        sentences=len(sentences),
        number_language=str(args.number_language),
        lexicon_status=args.lexique_statut,
        applied=result.applied,
    ).write(paths.run_info_json)
    write_human_template(result.records, paths.human_csv)
    logger.info(
        "%d audios prêts dans %s (cache : %d réutilisés, %d générés).",
        len(result.records),
        paths.audio_dir,
        tts.hits,
        tts.misses,
    )


def _report(args: argparse.Namespace) -> None:
    paths = OutputPaths(args.output_dir)
    build_report(paths)
    logger.info(
        "Rapport écrit : %s, %s et %s",
        paths.ranking_csv,
        paths.phrase_diagnostic_csv,
        paths.summary_md,
    )


def _check(args: argparse.Namespace) -> bool:
    from xamxam.eval.check import check_sentences, format_report

    # Pire cas pour la longueur : toutes les prononciations, même brouillon, appliquées.
    pipeline = XamXamPipeline.from_lexicon_file(args.lexicon, applied_statuses=VALIDATED_AND_DRAFT)
    report = check_sentences(load_sentences(args.sentences), pipeline)
    print(format_report(report))
    return report.ok


def _llm(args: argparse.Namespace) -> None:
    from xamxam.eval.llm_bench import (
        ConfiguredModel,
        load_configs,
        load_ground_truth,
        run_llm_benchmark,
        write_outputs,
    )
    from xamxam.lexicon import load_lexicon
    from xamxam.llm.factory import build_llm, build_rodium_llm
    from xamxam.whatsapp.settings import BotSettings

    settings = Settings.from_env()
    terms = [term.term for term in load_lexicon(args.lexicon).terms]
    max_chars = BotSettings().max_explanation_chars
    models = [
        ConfiguredModel(
            config,
            (
                build_rodium_llm(
                    config.model,
                    api_key=settings.rodium_api_key,
                    lexicon_terms=terms,
                    max_explanation_chars=max_chars,
                )
                if settings.rodium_api_key
                else build_llm(
                    config.model,
                    api_key=settings.gemini_api_key or "",
                    lexicon_terms=terms,
                    max_explanation_chars=max_chars,
                )
            ),
        )
        for config in load_configs(args.configs)
    ]
    cases = load_ground_truth(args.verite or args.photos / "verite_terrain.csv")
    records = run_llm_benchmark(
        cases, args.photos, models, repetitions=args.repetitions, on_progress=logger.info
    )
    write_outputs(records, args.output_dir, repetitions=args.repetitions)
    logger.info("Rapport écrit : %s", args.output_dir / "rapport.md")


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            _run(args)
        elif args.command == "audio":
            _audio(args)
        elif args.command == "llm":
            _llm(args)
        elif args.command == "check":
            return 0 if _check(args) else 1
        elif args.command == "blind":
            count = create_blind_sheet(
                OutputPaths(args.output_dir), seed=args.seed, overwrite=args.overwrite_blind
            )
            logger.info("Fiche aveugle créée : %d audios.", count)
        elif args.command == "unblind":
            count = import_blind_sheet(
                OutputPaths(args.output_dir), overwrite_human=args.overwrite_human
            )
            logger.info("Notes réintégrées : %d lignes annotées.", count)
        else:
            _report(args)
    except XamXamError as exc:
        logger.error("%s", exc)
        return 1
    return 0
