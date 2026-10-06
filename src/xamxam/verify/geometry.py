"""Recalcul des résultats de Pythagore et de Thalès avec sympy.

Le résultat annoncé par le modèle est accepté sous forme exacte (√52, 2√13, 9/2) comme
sous forme arrondie (7,21 ; 7,2) : un arrondi à n décimales est juste si l'écart avec la
valeur exacte ne dépasse pas une demi-unité de la dernière décimale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import sympy

from xamxam.llm.schema import Calculation, CalculationKind, MathSolution, Notion

_EXACT_TOLERANCE = 1e-9
_YES = {"oui", "vrai", "rectangle", "parallèles", "waaw"}
_NO = {"non", "faux", "déedéet"}

_NUMBER = r"\d+(?:[.,]\d+)?"
_SQRT = re.compile(rf"(?:({_NUMBER})\s*[×*]?\s*)?(?:√|sqrt)\s*\(?\s*({_NUMBER})\s*\)?")
_FRACTION = re.compile(rf"({_NUMBER})\s*/\s*({_NUMBER})")
_DECIMAL = re.compile(_NUMBER)


class VerificationStatus(StrEnum):
    VERIFIED = "verifie"
    MISMATCH = "desaccord"
    UNVERIFIED = "non_verifie"  # notion hors Pythagore / Thalès


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    expected: str | None = None  # valeur correcte, lisible, pour la consigne de correction
    reason: str = ""  # cause technique, sans contenu de l'élève


@dataclass(frozen=True)
class AnnouncedValue:
    value: sympy.Expr
    decimals: int | None  # None pour une forme exacte


def _rational(value: float | str) -> sympy.Rational:
    # Passer par la chaîne évite les artefacts binaires : 3.6 → 18/5 exactement.
    return sympy.Rational(str(value).replace(",", "."))


def _decimals(number: str) -> int:
    _, _, fraction = number.replace(",", ".").partition(".")
    return len(fraction)


def parse_announced(text: str) -> bool | list[AnnouncedValue] | None:
    """Lit le résultat annoncé : booléen (« oui » / « non »), liste de valeurs, ou None."""
    lowered = text.strip().lower()
    words = set(re.findall(r"[\wéè]+", lowered))
    if words & _YES and not words & _NO:
        return True
    if words & _NO and not words & _YES:
        return False

    values: list[AnnouncedValue] = []
    remaining = lowered
    for match in _SQRT.finditer(lowered):
        coefficient = _rational(match.group(1)) if match.group(1) else sympy.Integer(1)
        values.append(AnnouncedValue(coefficient * sympy.sqrt(_rational(match.group(2))), None))
    remaining = _SQRT.sub(" ", remaining)
    for match in _FRACTION.finditer(remaining):
        values.append(AnnouncedValue(_rational(match.group(1)) / _rational(match.group(2)), None))
    remaining = _FRACTION.sub(" ", remaining)
    for match in _DECIMAL.finditer(remaining):
        values.append(AnnouncedValue(_rational(match.group()), _decimals(match.group())))
    return values or None


def expected_result(calculation: Calculation) -> sympy.Expr | bool:
    """Recalcule le résultat exact à partir des données. ValueError si elles sont invalides."""
    kind = calculation.kind

    def get(*names: str) -> list[sympy.Rational]:
        values = [calculation.value(name) for name in names]
        if any(v is None for v in values):
            missing = [n for n, v in zip(names, values, strict=True) if v is None]
            raise ValueError(f"données manquantes : {', '.join(missing)}")
        rationals = [_rational(v) for v in values if v is not None]
        if any(v <= 0 for v in rationals):
            raise ValueError("longueur nulle ou négative")
        return rationals

    if kind is CalculationKind.PYTHAGORE_HYPOTENUSE:
        a, b = get("cote1", "cote2")
        return sympy.sqrt(a**2 + b**2)
    if kind is CalculationKind.PYTHAGORE_SIDE:
        hypotenuse, side = get("hypotenuse", "cote")
        if hypotenuse <= side:
            raise ValueError("l'hypoténuse doit être le plus long côté")
        return sympy.sqrt(hypotenuse**2 - side**2)
    if kind is CalculationKind.PYTHAGORE_CONVERSE:
        a, b, c = sorted(get("a", "b", "c"))
        return bool(a**2 + b**2 == c**2)
    if kind is CalculationKind.THALES_LENGTH:
        a, b, c = get("a", "b", "c")
        return b * c / a
    if kind is CalculationKind.THALES_CONVERSE:
        a, b, c, d = get("a", "b", "c", "d")
        return bool(a / b == c / d)
    raise ValueError("aucun calcul vérifiable")


def format_expected(value: sympy.Expr | bool) -> str:
    """Écriture lisible : « 2√13 ≈ 7,21 », « 4,5 », « oui »."""
    if isinstance(value, bool):
        return "oui" if value else "non"
    value = sympy.nsimplify(value)
    approx = f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    if value.is_Rational:
        return approx if value.q != 1 else str(value.p)
    coefficient, radical = value.as_coeff_Mul()
    if isinstance(radical, sympy.Pow) and radical.exp == sympy.Rational(1, 2):
        prefix = "" if coefficient == 1 else str(coefficient)
        return f"{prefix}√{radical.base} ≈ {approx}"
    return f"{sympy.sstr(value)} ≈ {approx}"


def _matches(announced: AnnouncedValue, expected: sympy.Expr) -> bool:
    difference = abs(float(announced.value) - float(expected))
    if announced.decimals is None:
        return difference < _EXACT_TOLERANCE
    return difference <= 0.5 * 10 ** (-announced.decimals) + _EXACT_TOLERANCE


def verify_solution(solution: MathSolution) -> VerificationResult:
    """Compare le résultat annoncé au recalcul sympy (Pythagore et Thalès uniquement)."""
    if solution.notion not in (Notion.PYTHAGORE, Notion.THALES):
        return VerificationResult(VerificationStatus.UNVERIFIED, reason="notion non vérifiable")
    calculation = solution.calculation
    try:
        expected = expected_result(calculation)
    except ValueError as exc:
        return VerificationResult(VerificationStatus.MISMATCH, reason=str(exc))

    readable = format_expected(expected)
    announced = parse_announced(calculation.result)
    if announced is None:
        return VerificationResult(VerificationStatus.MISMATCH, readable, "résultat illisible")
    if isinstance(expected, bool) or isinstance(announced, bool):
        ok = isinstance(expected, bool) and isinstance(announced, bool) and expected == announced
    else:
        # Toutes les formes annoncées (exacte et arrondie) doivent être justes.
        ok = all(_matches(value, expected) for value in announced)
    if ok:
        return VerificationResult(VerificationStatus.VERIFIED, readable)
    return VerificationResult(VerificationStatus.MISMATCH, readable, "résultat différent")
