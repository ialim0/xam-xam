import pytest

from fakes import make_solution
from xamxam.llm import Calculation
from xamxam.verify import (
    VerificationStatus,
    expected_result,
    format_expected,
    parse_announced,
    verify_solution,
)


def _calc(kind: str, result: str, **values: float) -> dict:
    return {
        "type": kind,
        "donnees": [{"nom": k, "valeur": v} for k, v in values.items()],
        "resultat": result,
    }


@pytest.mark.parametrize(
    "result", ["√52 ≈ 7,21", "√52", "2√13", "sqrt(52)", "7,21", "7,2", "7.21 cm", "BC = √52"]
)
def test_irrational_results_accept_exact_and_rounded_forms(result: str) -> None:
    solution = make_solution(resultat=result)
    assert verify_solution(solution).status is VerificationStatus.VERIFIED


@pytest.mark.parametrize("result", ["7,5", "√50", "√52 ≈ 7,5", "7,22", "pas de résultat"])
def test_wrong_results_are_detected(result: str) -> None:
    verification = verify_solution(make_solution(resultat=result))
    assert verification.status is VerificationStatus.MISMATCH
    assert verification.expected == "2√13 ≈ 7,21"


@pytest.mark.parametrize(
    ("calcul", "expected"),
    [
        (_calc("pythagore_hypotenuse", "5", cote1=3, cote2=4), "5"),
        (_calc("pythagore_cote", "4,8", hypotenuse=6, cote=3.6), "4,8"),
        (_calc("pythagore_reciproque", "oui", a=5, b=3, c=4), "oui"),
        (_calc("pythagore_reciproque", "non", a=2, b=3, c=4), "non"),
        (_calc("thales_longueur", "4,5", a=2, b=6, c=1.5), "4,5"),
        (_calc("thales_longueur", "9/2", a=2, b=6, c=1.5), "4,5"),
        (_calc("thales_reciproque", "oui, les droites sont parallèles", a=2, b=6, c=1, d=3), "oui"),
    ],
)
def test_calculation_kinds(calcul: dict, expected: str) -> None:
    notion = "thales" if calcul["type"].startswith("thales") else "pythagore"
    verification = verify_solution(make_solution(notion=notion, calcul=calcul))
    assert verification.status is VerificationStatus.VERIFIED
    assert verification.expected == expected


def test_boolean_mismatch() -> None:
    calcul = _calc("pythagore_reciproque", "non", a=3, b=4, c=5)
    assert verify_solution(make_solution(calcul=calcul)).status is VerificationStatus.MISMATCH


@pytest.mark.parametrize(
    ("calcul", "reason"),
    [
        (_calc("pythagore_hypotenuse", "5", cote1=3), "données manquantes : cote2"),
        (_calc("pythagore_cote", "5", hypotenuse=3, cote=4), "plus long côté"),
        (_calc("pythagore_hypotenuse", "5", cote1=0, cote2=4), "nulle ou négative"),
        (_calc("aucun", ""), "aucun calcul vérifiable"),
    ],
)
def test_invalid_data_is_a_mismatch(calcul: dict, reason: str) -> None:
    verification = verify_solution(make_solution(calcul=calcul))
    assert verification.status is VerificationStatus.MISMATCH
    assert reason in verification.reason


def test_other_notions_are_not_verified() -> None:
    solution = make_solution(notion="autre", calcul=_calc("aucun", ""))
    assert verify_solution(solution).status is VerificationStatus.UNVERIFIED


def test_parse_and_format_helpers() -> None:
    assert parse_announced("Oui, il est rectangle") is True
    assert parse_announced("non") is False
    assert parse_announced("rien") is None
    calc = Calculation.model_validate(_calc("pythagore_cote", "", hypotenuse=10, cote=6))
    assert format_expected(expected_result(calc)) == "8"
    assert format_expected(True) == "oui"
