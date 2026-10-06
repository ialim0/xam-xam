"""Écriture des nombres entiers en toutes lettres (français, orthographe traditionnelle)."""

from __future__ import annotations

_UNITS = (
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
)  # fmt: skip
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}

# Au-delà, on laisse les chiffres tels quels : ces nombres sont rares dans les exercices.
MAX_SPELLED = 999_999_999


def _below_100(n: int) -> str:
    if n < 17:
        return _UNITS[n]
    if n < 20:
        return "dix-" + _UNITS[n - 10]
    tens, unit = divmod(n, 10)
    if tens == 7:
        # 70 à 79 : soixante-dix, soixante et onze, soixante-douze…
        return "soixante et onze" if unit == 1 else "soixante-" + _below_100(10 + unit)
    if tens == 8:
        return "quatre-vingts" if unit == 0 else "quatre-vingt-" + _UNITS[unit]
    if tens == 9:
        return "quatre-vingt-" + _below_100(10 + unit)
    word = _TENS[tens]
    if unit == 0:
        return word
    if unit == 1:
        return word + " et un"
    return word + "-" + _UNITS[unit]


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if hundreds == 0:
        return _below_100(rest)
    head = "cent" if hundreds == 1 else _UNITS[hundreds] + " cent"
    if rest == 0:
        # « deux cents » prend un s, mais pas « cent ».
        return head + ("s" if hundreds > 1 else "")
    return head + " " + _below_100(rest)


def _before_mille(n: int) -> str:
    # « mille » est invariable et fait perdre le s de « cents » / « quatre-vingts ».
    words = _below_1000(n)
    return words[:-1] if words.endswith(("cents", "vingts")) else words


def spell_french_number(n: int) -> str:
    """Écrit un entier positif en lettres, ex. 71 → « soixante et onze ».

    Les nombres négatifs ou supérieurs à MAX_SPELLED sont rendus en chiffres.
    """
    if n < 0 or n > MAX_SPELLED:
        return str(n)
    if n == 0:
        return _UNITS[0]
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    parts: list[str] = []
    if millions:
        parts.append("un million" if millions == 1 else _below_1000(millions) + " millions")
    if thousands:
        parts.append("mille" if thousands == 1 else _before_mille(thousands) + " mille")
    if units:
        parts.append(_below_1000(units))
    return " ".join(parts)
