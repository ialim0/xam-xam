"""Autocontrôle TTS → STT des éléments mathématiques audibles.

Le STT transcrit souvent « bee see » en « BC ». Ces graphies sont équivalentes pour
contrôler une formule. Le contrôle reste un indicateur machine, pas une validation
linguistique de la prononciation.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import wave
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from xamxam.normalize.tables import FRENCH
from xamxam.providers.base import ProviderError, STTProvider, TTSProvider

logger = logging.getLogger(__name__)

_POINT = re.compile(r"(?<![\w'’])[A-Z]{2,3}(?:(?![\w'’])|(?=[²³]))")
_SQUARE = re.compile(r"²|\^\s*2")
_HEARD_SQUARE = re.compile(
    r"(?<!\w)(?:(?:au|o)\s+(?:carre|kare|kaare)|puissance\s+(?:2|deux))(?!\w)"
)
_HEARD_EQUAL = re.compile(r"(?<!\w)egal(?:e|\s+a)?(?!\w)")
_HEARD_PLUS = re.compile(r"(?<!\w)plus(?!\w)")
_HEARD_ROOT = re.compile(r"(?<!\w)racine(?:\s+carree)?(?!\w)")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[-’']", " ", plain)).strip()


def _point_aliases(point: str) -> set[str]:
    names = FRENCH.letter_names
    aliases = {
        point.casefold(),
        " ".join(point.casefold()),
        " ".join(names[letter] for letter in point),
        "".join(names[letter] for letter in point),
    }
    if len(point) == 3:
        aliases |= {
            f"{point[:2].casefold()} {point[2].casefold()}",
            f"{point[0].casefold()} {point[1:].casefold()}",
        }
    return {_fold(alias) for alias in aliases}


def _heard_points(transcript: str, points: Counter[str]) -> Counter[str]:
    folded = _fold(transcript)
    matches: list[tuple[int, int, str]] = []
    for point in points:
        for alias in _point_aliases(point):
            pattern = re.compile(
                r"(?<!\w)" + r"\s+".join(map(re.escape, alias.split())) + r"(?!\w)"
            )
            matches.extend(
                (match.start(), match.end(), point) for match in pattern.finditer(folded)
            )
    # Les noms à trois lettres sont pris avant leurs sous-séquences à deux lettres.
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    heard: Counter[str] = Counter()
    end = -1
    for start, stop, point in matches:
        if start >= end:
            heard[point] += 1
            end = stop
    return heard


@dataclass(frozen=True)
class AnchorCheck:
    kind: str
    value: str
    expected: int
    heard: int

    @property
    def missing(self) -> int:
        return max(0, self.expected - self.heard)


def check_math_audio(source: str, transcript: str) -> tuple[AnchorCheck, ...]:
    """Compare les marqueurs mathématiques de la source à leur transcription STT.

    Les lettres isolées sont exclues : « a » est trop fréquent dans une phrase wolof
    pour prouver que le point A a été prononcé.
    """
    expected_points = Counter(match.group() for match in _POINT.finditer(source))
    heard_points = _heard_points(transcript, expected_points)
    checks = [
        AnchorCheck("point", point, count, min(count, heard_points[point]))
        for point, count in sorted(expected_points.items())
    ]
    folded = _fold(transcript)
    for kind, expected, pattern in (
        ("carre", len(_SQUARE.findall(source)), _HEARD_SQUARE),
        ("egal", source.count("="), _HEARD_EQUAL),
        ("plus", source.count("+"), _HEARD_PLUS),
        ("racine", source.count("√"), _HEARD_ROOT),
    ):
        if expected:
            checks.append(
                AnchorCheck(kind, kind, expected, min(expected, len(pattern.findall(folded))))
            )
    return tuple(checks)


def _variants(text: str, missing: tuple[AnchorCheck, ...]) -> list[str]:
    variants: list[str] = []
    for check in missing:
        if check.kind == "point":
            names = " ".join(FRENCH.letter_names[letter] for letter in check.value)
            variant = re.sub(
                r"(?<!\w)" + re.escape(names) + r"(?!\w)", names.replace(" ", "-"), text
            )
        elif check.kind == "carre":
            variant = text.replace("au carré", "puissance deux")
        elif check.kind == "egal":
            variant = text.replace("égale", "égal à")
        elif check.kind == "plus":
            variant = re.sub(r"(?<!\w)plus(?!\w)", ", plus,", text)
        elif check.kind == "racine":
            variant = re.sub(r"(?<!la )racine carrée de", "la racine carrée de", text)
        else:
            continue
        if variant != text and variant not in variants:
            variants.append(variant)
    return variants


def _short_enough(audio: bytes) -> bool:
    try:
        with wave.open(BytesIO(audio), "rb") as wav:
            return wav.getnframes() / wav.getframerate() <= 55
    except (wave.Error, ZeroDivisionError):
        return False


@dataclass(frozen=True)
class CheckedAudio:
    audio: bytes
    text: str
    baseline_heard: int
    final_heard: int
    expected: int
    trials: int


def synthesize_checked(
    source: str,
    text: str,
    *,
    tts: TTSProvider,
    stt: STTProvider,
    language: str = "wo",
    max_trials: int = 2,
) -> CheckedAudio:
    """Garde une variante seulement si le STT retrouve davantage de marqueurs sans régression.

    Le premier WAV est conservé si le STT échoue, si l'audio dépasse 55 s ou si
    aucune variante n'améliore la couverture. Aucun contenu n'est journalisé.
    """
    audio = tts.synthesize(text, language=language)
    anchors = check_math_audio(source, "")
    expected = sum(check.expected for check in anchors)
    if not expected or not _short_enough(audio):
        return CheckedAudio(audio, text, 0, 0, expected, 0)
    try:
        transcript = stt.transcribe(audio, language=language)
    except ProviderError:
        logger.warning("Autocontrôle STT indisponible ; audio initial conservé.")
        return CheckedAudio(audio, text, 0, 0, expected, 0)
    baseline = check_math_audio(source, transcript)
    best = baseline
    best_audio, best_text = audio, text
    trials = 0
    tried: set[str] = set()
    while trials < max_trials:
        variants = _variants(best_text, tuple(check for check in best if check.missing))
        variant = next((candidate for candidate in variants if candidate not in tried), None)
        if variant is None:
            break
        tried.add(variant)
        try:
            candidate_audio = tts.synthesize(variant, language=language)
            trials += 1
            if not _short_enough(candidate_audio):
                continue
            candidate = check_math_audio(source, stt.transcribe(candidate_audio, language=language))
        except ProviderError:
            logger.warning("Essai d'autocorrection audio échoué ; meilleur audio conservé.")
            break
        if all(new.heard >= old.heard for old, new in zip(best, candidate, strict=True)) and any(
            new.heard > old.heard for old, new in zip(best, candidate, strict=True)
        ):
            best, best_audio, best_text = candidate, candidate_audio, variant
    baseline_heard = sum(check.heard for check in baseline)
    final_heard = sum(check.heard for check in best)
    logger.info(
        "Autocontrôle formule : %d/%d marqueurs reconnus, %d/%d après %d essai(s).",
        baseline_heard,
        expected,
        final_heard,
        expected,
        trials,
    )
    return CheckedAudio(best_audio, best_text, baseline_heard, final_heard, expected, trials)
