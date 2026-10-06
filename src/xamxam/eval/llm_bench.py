"""Évaluation comparative des modèles de langage sur des photos d'exercices.

Entrées :
- un dossier de photos et un fichier verite_terrain.csv
  (fichier, type_image, notion, type_calcul, donnees, resultat_attendu) ;
- un fichier JSON de configurations à comparer (provider, modèle, prix par million de jetons).
Chaque photo est soumise `repetitions` fois à chaque configuration pour mesurer la stabilité.

Métriques par appel : JSON valide du premier coup, données correctement extraites, résultat
correct après recalcul sympy, latence, jetons et coût estimé. Sorties : resultats.csv,
notation_wolof.csv (à remplir à la main) et rapport.md.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import mimetypes
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from statistics import median

from xamxam.errors import XamXamError
from xamxam.llm import (
    Calculation,
    CalculationKind,
    KnownValue,
    LLMError,
    LLMProvider,
    MathSolution,
    ProblemInput,
)
from xamxam.verify import VerificationStatus, parse_announced, verify_solution

logger = logging.getLogger(__name__)

GROUND_TRUTH_COLUMNS = (
    "fichier",
    "type_image",
    "notion",
    "type_calcul",
    "donnees",
    "resultat_attendu",
)
_RELATIVE_TOLERANCE = 1e-6


class ImageType(StrEnum):
    PRINTED = "imprime"
    HANDWRITTEN = "manuscrit"


class BenchmarkError(XamXamError):
    """Vérité terrain ou configuration invalide."""


@dataclass(frozen=True)
class GroundTruthCase:
    file: str
    image_type: ImageType
    notion: str
    kind: CalculationKind
    values: dict[str, float]
    expected_result: str


@dataclass(frozen=True)
class ModelConfig:
    """Une configuration à comparer. Les prix sont fournis par l'utilisateur (aucun en dur)."""

    name: str
    provider: str
    model: str
    region: str | None = None
    base_url: str | None = None
    price_input_per_million: float | None = None
    price_output_per_million: float | None = None

    def cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.price_input_per_million is None or self.price_output_per_million is None:
            return None
        return (
            input_tokens * self.price_input_per_million
            + output_tokens * self.price_output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class BenchRecord:
    config: str
    file: str
    image_type: ImageType
    repetition: int
    json_valid: bool
    json_first_try: bool
    extraction_ok: bool
    result_ok: bool
    answer_key: str  # réponse normalisée, pour mesurer la stabilité
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost: float | None
    explanation_wo: str = ""
    error: str = ""


# --- Lecture des entrées -------------------------------------------------------------


def parse_values(raw: str) -> dict[str, float]:
    """« cote1=4;cote2=6,5 » → {"cote1": 4.0, "cote2": 6.5}."""
    values = {}
    for item in filter(None, (part.strip() for part in raw.split(";"))):
        name, sep, number = item.partition("=")
        if not sep:
            raise ValueError(f"donnée sans « = » : {item}")
        values[name.strip()] = float(number.strip().replace(",", "."))
    return values


def load_ground_truth(path: Path) -> list[GroundTruthCase]:
    try:
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            missing = set(GROUND_TRUTH_COLUMNS) - set(reader.fieldnames or ())
            if missing:
                raise BenchmarkError(f"{path} : colonnes manquantes : {', '.join(sorted(missing))}")
            cases = []
            for row in reader:
                where = f"{path}, ligne {reader.line_num}"
                try:
                    cases.append(
                        GroundTruthCase(
                            file=row["fichier"].strip(),
                            image_type=ImageType(row["type_image"].strip()),
                            notion=row["notion"].strip(),
                            kind=CalculationKind(row["type_calcul"].strip()),
                            values=parse_values(row["donnees"]),
                            expected_result=row["resultat_attendu"].strip(),
                        )
                    )
                except ValueError as exc:
                    raise BenchmarkError(f"{where} : {exc}") from exc
    except OSError as exc:
        raise BenchmarkError(f"Impossible de lire {path} : {exc}") from exc
    return cases


def load_configs(path: Path) -> list[ModelConfig]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            ModelConfig(
                name=item["nom"],
                provider=item["provider"],
                model=item["modele"],
                region=item.get("region"),
                base_url=item.get("base_url"),
                price_input_per_million=item.get("prix_entree_par_million"),
                price_output_per_million=item.get("prix_sortie_par_million"),
            )
            for item in raw
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BenchmarkError(f"Configurations illisibles ({path}) : {exc}") from exc


# --- Notation d'un appel -----------------------------------------------------------------


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=_RELATIVE_TOLERANCE, abs_tol=1e-9)


def extraction_correct(solution: MathSolution, case: GroundTruthCase) -> bool:
    """Bon type de calcul, et chaque donnée attendue lue avec la bonne valeur."""
    calculation = solution.calculation
    if calculation.kind is not case.kind:
        return False
    read = {v.name: v.value for v in calculation.values}
    return all(name in read and _close(read[name], value) for name, value in case.values.items())


def result_correct(solution: MathSolution, case: GroundTruthCase) -> bool:
    """Le résultat annoncé est comparé au recalcul sympy fait à partir de la vérité terrain."""
    reference = Calculation(
        kind=case.kind,
        values=[KnownValue(name=k, value=v) for k, v in case.values.items()],
        result=solution.calculation.result,
    )
    checked = solution.model_copy(update={"calculation": reference})
    return verify_solution(checked).status is VerificationStatus.VERIFIED


def answer_key(solution: MathSolution) -> str:
    announced = parse_announced(solution.calculation.result)
    if isinstance(announced, bool):
        return "oui" if announced else "non"
    if not announced:
        return "illisible"
    return f"{float(announced[0].value):.2f}"


# --- Exécution -----------------------------------------------------------------------------


@dataclass
class ConfiguredModel:
    config: ModelConfig
    provider: LLMProvider


def run_llm_benchmark(
    cases: Sequence[GroundTruthCase],
    photos_dir: Path,
    models: Sequence[ConfiguredModel],
    *,
    repetitions: int = 3,
    on_progress: Callable[[str], None] | None = None,
) -> list[BenchRecord]:
    if repetitions < 1:
        raise BenchmarkError("--repetitions doit valoir au moins 1.")
    records = []
    for case in cases:
        path = photos_dir / case.file
        try:
            image = path.read_bytes()
        except OSError as exc:
            raise BenchmarkError(f"Photo illisible : {path}") from exc
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        problem = ProblemInput(image=image, image_mime_type=mime)
        for model in models:
            for repetition in range(1, repetitions + 1):
                records.append(_evaluate(model, case, problem, repetition))
            if on_progress:
                on_progress(f"{model.config.name} : {case.file}")
    return records


def _evaluate(
    model: ConfiguredModel, case: GroundTruthCase, problem: ProblemInput, repetition: int
) -> BenchRecord:
    base = {
        "config": model.config.name,
        "file": case.file,
        "image_type": case.image_type,
        "repetition": repetition,
    }
    try:
        result = model.provider.generate(problem)
    except LLMError as exc:
        return BenchRecord(
            **base,
            json_valid=False,
            json_first_try=False,
            extraction_ok=False,
            result_ok=False,
            answer_key="echec",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost=None,
            error=type(exc).__name__,
        )
    solution, stats = result.solution, result.stats
    return BenchRecord(
        **base,
        json_valid=True,
        json_first_try=stats.json_valid_first_try,
        extraction_ok=extraction_correct(solution, case),
        result_ok=result_correct(solution, case),
        answer_key=answer_key(solution),
        latency_ms=stats.latency_ms,
        input_tokens=stats.input_tokens,
        output_tokens=stats.output_tokens,
        cost=model.config.cost(stats.input_tokens, stats.output_tokens),
        explanation_wo=solution.explanation_wo,
    )


# --- Agrégation et rapport ---------------------------------------------------------------


@dataclass
class ConfigSummary:
    name: str
    calls: int = 0
    json_first_try: int = 0
    json_valid: int = 0
    extraction_ok: int = 0
    result_ok: int = 0
    stability: float | None = None
    latency_median_ms: float | None = None
    latency_p95_ms: float | None = None
    mean_cost: float | None = None
    result_by_image_type: dict[ImageType, tuple[int, int]] = field(default_factory=dict)


def _percentile(values: Sequence[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)])


def summarize(records: Sequence[BenchRecord]) -> list[ConfigSummary]:
    by_config: dict[str, list[BenchRecord]] = defaultdict(list)
    for record in records:
        by_config[record.config].append(record)
    summaries = []
    for name, items in by_config.items():
        summary = ConfigSummary(name=name, calls=len(items))
        summary.json_first_try = sum(r.json_first_try for r in items)
        summary.json_valid = sum(r.json_valid for r in items)
        summary.extraction_ok = sum(r.extraction_ok for r in items)
        summary.result_ok = sum(r.result_ok for r in items)
        # Stabilité : part des répétitions qui donnent la réponse majoritaire, par photo.
        per_case: dict[str, list[str]] = defaultdict(list)
        for record in items:
            per_case[record.file].append(record.answer_key)
        shares = [Counter(keys).most_common(1)[0][1] / len(keys) for keys in per_case.values()]
        summary.stability = sum(shares) / len(shares) if shares else None
        latencies = [r.latency_ms for r in items if r.json_valid]
        summary.latency_median_ms = float(median(latencies)) if latencies else None
        summary.latency_p95_ms = _percentile(latencies, 0.95)
        costs = [r.cost for r in items if r.cost is not None]
        summary.mean_cost = sum(costs) / len(costs) if costs else None
        for image_type in ImageType:
            subset = [r for r in items if r.image_type is image_type]
            if subset:
                summary.result_by_image_type[image_type] = (
                    sum(r.result_ok for r in subset),
                    len(subset),
                )
        summaries.append(summary)
    return sorted(summaries, key=lambda s: (-s.result_ok / s.calls, s.name))


_RESULT_COLUMNS = (
    "configuration",
    "fichier",
    "type_image",
    "repetition",
    "json_valide",
    "json_premier_coup",
    "extraction_correcte",
    "resultat_correct",
    "reponse",
    "latence_ms",
    "jetons_entree",
    "jetons_sortie",
    "cout_estime",
    "erreur",
)
_RATING_COLUMNS = (
    "configuration",
    "fichier",
    "repetition",
    "explication_wo",
    "note_wolof",
    "note_clarte",
    "commentaire",
)


def write_outputs(records: Sequence[BenchRecord], output_dir: Path, *, repetitions: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "resultats.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(_RESULT_COLUMNS)
        for r in records:
            writer.writerow(
                (
                    r.config,
                    r.file,
                    r.image_type,
                    r.repetition,
                    int(r.json_valid),
                    int(r.json_first_try),
                    int(r.extraction_ok),
                    int(r.result_ok),
                    r.answer_key,
                    r.latency_ms,
                    r.input_tokens,
                    r.output_tokens,
                    "" if r.cost is None else f"{r.cost:.6f}",
                    r.error,
                )
            )
    rating = output_dir / "notation_wolof.csv"
    if rating.exists():
        logger.warning("%s existe déjà : conservé (notes saisies à la main).", rating)
    else:
        with rating.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(_RATING_COLUMNS)
            for r in records:
                if r.json_valid:
                    writer.writerow((r.config, r.file, r.repetition, r.explanation_wo, "", "", ""))
    (output_dir / "rapport.md").write_text(
        render_report(summarize(records), repetitions=repetitions), encoding="utf-8"
    )


def _pct(count: int, total: int) -> str:
    return "n/d" if total == 0 else f"{100 * count / total:.0f} %"


def _num(value: float | None, unit: str = "", digits: int = 0) -> str:
    if value is None:
        return "n/d"
    return f"{value:.{digits}f}{unit}".replace(".", ",")


def render_report(summaries: Sequence[ConfigSummary], *, repetitions: int) -> str:
    lines = [
        "# Évaluation des modèles de langage",
        "",
        f"Chaque photo a été soumise {repetitions} fois à chaque configuration.",
        "",
        "| Configuration | Appels | JSON 1er coup | JSON valide | Données extraites | "
        "Résultat correct (sympy) | Stabilité | Latence médiane | Latence p95 | Coût moyen |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        lines.append(
            f"| {s.name} | {s.calls} | {_pct(s.json_first_try, s.calls)} "
            f"| {_pct(s.json_valid, s.calls)} | {_pct(s.extraction_ok, s.calls)} "
            f"| {_pct(s.result_ok, s.calls)} "
            f"| {_num(None if s.stability is None else 100 * s.stability, ' %')} "
            f"| {_num(s.latency_median_ms, ' ms')} | {_num(s.latency_p95_ms, ' ms')} "
            f"| {_num(s.mean_cost, ' $', 5)} |"
        )
    lines += [
        "",
        "## Résultat correct selon le type d'image",
        "",
        "| Configuration | Imprimé | Manuscrit |",
        "| --- | --- | --- |",
    ]
    for s in summaries:
        cells = [_pct(*s.result_by_image_type.get(t, (0, 0))) for t in ImageType]
        lines.append(f"| {s.name} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        "Stabilité : part des répétitions qui donnent la réponse majoritaire, moyennée par photo.",
        "Coût : jetons mesurés × prix indiqués dans le fichier de configurations.",
        "La qualité du wolof se note dans `notation_wolof.csv`.",
        "",
    ]
    return "\n".join(lines)
