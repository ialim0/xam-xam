"""Vérification symbolique (sympy) des résultats numériques des exercices."""

from xamxam.verify.geometry import (
    VerificationResult,
    VerificationStatus,
    expected_result,
    format_expected,
    parse_announced,
    verify_solution,
)

__all__ = [
    "VerificationResult",
    "VerificationStatus",
    "expected_result",
    "format_expected",
    "parse_announced",
    "verify_solution",
]
