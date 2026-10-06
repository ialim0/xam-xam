import pytest

from xamxam.lexicon import Lexicon
from xamxam.lexicon.check import find_alphabet_issues, format_issues
from xamxam.normalize import MathNormalizer, NumberLanguage, spell_french_number, spell_wolof_number
from xamxam.tts_alphabet import unsupported_characters


def test_unsupported_characters() -> None:
    assert unsupported_characters("AB² = √25 + π") == sorted("25=+²π√")
    assert unsupported_characters("Ñaar fukk, juróom ŋ ë") == []
    # Le pulaar a ses propres lettres ; le « ó » wolof (juróom) n'en fait pas partie.
    assert unsupported_characters("ɓ ɗ ƴ", "ff") == []
    assert unsupported_characters("ɓ", "wo") == ["ɓ"]
    assert unsupported_characters("juróom", "ff") == ["ó"]


def test_unknown_alphabet() -> None:
    with pytest.raises(ValueError, match="srr"):
        unsupported_characters("texte", "srr")


def test_lexicon_only_uses_tts_alphabet(lexicon: Lexicon) -> None:
    """Signale tout terme dont une graphie ou la prononciation contient un caractère
    que le TTS ignorerait silencieusement."""
    issues = find_alphabet_issues(lexicon)
    assert not issues, format_issues(issues)


def test_alphabet_issues_are_reported() -> None:
    lexicon = Lexicon.model_validate(
        {
            "version": "t",
            "language": "wo",
            "terms": [{"term": "AB²", "pronunciation": "a b ñaar", "aliases": ["x²"]}],
        }
    )
    issues = find_alphabet_issues(lexicon)
    assert [(i.field, i.characters) for i in issues] == [("term", ("²",)), ("alias", ("²",))]
    assert "AB² [term]" in format_issues(issues)


@pytest.mark.parametrize("spell", [spell_french_number, spell_wolof_number])
def test_spelled_numbers_use_tts_alphabet(spell) -> None:
    for number in [*range(0, 1200), 2026, 80_000, 999_999]:
        assert unsupported_characters(spell(number)) == [], number


@pytest.mark.parametrize("number_language", list(NumberLanguage))
def test_normalized_math_uses_tts_alphabet(number_language: NumberLanguage) -> None:
    normalizer = MathNormalizer(number_language=number_language)
    text = normalizer.normalize("BC² = AB² + AC² = 3,6² + 4,8² ; √25 = 5 ; 3/4 ; 30° ; 12 km/h")
    assert unsupported_characters(text) == []
