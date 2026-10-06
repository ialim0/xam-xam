import pytest

from xamxam.normalize import (
    MathNormalizer,
    NormalizationMode,
    NumberLanguage,
    UnknownLanguageError,
    get_table,
    spell_french_number,
    spell_wolof_number,
)


@pytest.fixture
def normalizer() -> MathNormalizer:
    return MathNormalizer()


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "zéro"),
        (1, "un"),
        (16, "seize"),
        (17, "dix-sept"),
        (21, "vingt et un"),
        (70, "soixante-dix"),
        (71, "soixante et onze"),
        (77, "soixante-dix-sept"),
        (80, "quatre-vingts"),
        (81, "quatre-vingt-un"),
        (91, "quatre-vingt-onze"),
        (100, "cent"),
        (200, "deux cents"),
        (201, "deux cent un"),
        (1000, "mille"),
        (2024, "deux mille vingt-quatre"),
        (80_000, "quatre-vingt mille"),
        (200_000, "deux cent mille"),
        (1_000_000, "un million"),
        (3_000_200, "trois millions deux cents"),
    ],
)
def test_spell_french_number(number: int, words: str) -> None:
    assert spell_french_number(number) == words


def test_spell_french_number_out_of_range() -> None:
    assert spell_french_number(10**9) == "1000000000"
    assert spell_french_number(-3) == "-3"


def test_raw_mode_keeps_symbols(normalizer: MathNormalizer) -> None:
    text = "BC = √25 cm, AB² = 3,6"
    assert normalizer.normalize(text, NormalizationMode.RAW) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AB²", "A B au carré"),
        ("BC = 5 cm", "B C égale cinq centimètres"),
        ("√25", "racine carrée de vingt-cinq"),
        ("3,6", "trois virgule six"),
        ("3.6", "trois virgule six"),
        ("3,05", "trois virgule zéro cinq"),
        ("3/4", "trois sur quatre"),
        ("AB/AC", "A B sur A C"),
        ("1 cm", "un centimètre"),
        ("1,5 m", "un virgule cinq mètre"),
        ("2,5 m", "deux virgule cinq mètres"),
        ("9 cm²", "neuf centimètres carrés"),
        ("12km/h", "douze kilomètres par heure"),
        ("30°", "trente degrés"),
        ("x^2 + x^3 + x^4", "x au carré plus x au cube plus x puissance quatre"),
        ("a⁴", "a puissance quatre"),
        ("a - b", "a moins b"),
        ("5-3", "cinq moins trois"),
        ("-3", "moins trois"),
        ("½", "un demi"),
        ("(AB) // (CD)", "(A B) parallèle à (C D)"),
        ("BC² = AB² + AC².", "B C au carré égale A B au carré plus A C au carré."),
    ],
)
def test_normalize_expressions(normalizer: MathNormalizer, text: str, expected: str) -> None:
    assert normalizer.normalize(text) == expected


def test_words_are_left_untouched(normalizer: MathNormalizer) -> None:
    text = "C'est-à-dire que le triangle est rectangle, 5 minutes plus tard."
    assert normalizer.normalize(text) == (
        "C'est-à-dire que le triangle est rectangle, cinq minutes plus tard."
    )


def test_unknown_reading_language() -> None:
    with pytest.raises(UnknownLanguageError, match="locuteurs natifs"):
        get_table("wo")


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "tus"),
        (5, "juróom"),
        (7, "juróom ñaar"),
        (10, "fukk"),
        (11, "fukk ak benn"),
        (25, "ñaar fukk ak juróom"),
        (70, "juróom ñaar fukk"),
        (100, "téeméer"),
        (125, "téeméer ak ñaar fukk ak juróom"),
        (200, "ñaar téeméer"),
        (1000, "junni"),
        (2026, "ñaar junni ak ñaar fukk ak juróom benn"),
        (250_000, "ñaar téeméer ak juróom fukk junni"),
    ],
)
def test_spell_wolof_number(number: int, words: str) -> None:
    assert spell_wolof_number(number) == words


def test_spell_wolof_number_out_of_range() -> None:
    assert spell_wolof_number(1_000_000) == "1000000"
    assert spell_wolof_number(-1) == "-1"


@pytest.mark.parametrize(
    ("number_language", "expected"),
    [
        (NumberLanguage.FRENCH, "B C égale vingt-cinq centimètres, trois virgule zéro cinq"),
        (
            NumberLanguage.WOLOF,
            "B C égale ñaar fukk ak juróom centimètres, ñett virgule tus juróom",
        ),
    ],
)
def test_number_language_modes(number_language: NumberLanguage, expected: str) -> None:
    normalizer = MathNormalizer(number_language=number_language)
    assert normalizer.normalize("BC = 25 cm, 3,05") == expected
