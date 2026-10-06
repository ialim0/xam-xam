import pytest

from xamxam.lexicon import LexiconIndex
from xamxam.translate import (
    TranslationError,
    Translator,
    protect_terms,
    restore_terms,
    translate_protected,
)


class FakeTranslator(Translator):
    name = "faux"

    def __init__(self, transform) -> None:
        self.transform = transform
        self.received: list[str] = []

    def translate(self, text: str, *, source: str = "fr", target: str = "wo") -> str:
        self.received.append(text)
        return self.transform(text)


TEXT = "Dans un triangle rectangle, l'hypoténuse est le plus grand côté du triangle rectangle."


def test_terms_are_protected_with_unique_markers(index: LexiconIndex) -> None:
    protected = protect_terms(TEXT, index)
    assert protected.text == "Dans un ⟦T1⟧, l'⟦T2⟧ est le plus grand côté du ⟦T3⟧."
    assert protected.markers == {
        "⟦T1⟧": "triangle rectangle",
        "⟦T2⟧": "hypoténuse",
        "⟦T3⟧": "triangle rectangle",
    }


def test_translation_restores_terms(index: LexiconIndex) -> None:
    translator = FakeTranslator(
        lambda t: t.replace("Dans un", "Ci benn").replace(
            "est le plus grand côté du", "mooy wet bi gën a gudd ci"
        )
    )
    result = translate_protected(TEXT, translator, index)
    assert (
        result
        == "Ci benn triangle rectangle, l'hypoténuse mooy wet bi gën a gudd ci triangle rectangle."
    )
    assert "hypoténuse" not in translator.received[0]


@pytest.mark.parametrize(
    ("transform", "message"),
    [
        (lambda t: t.replace("⟦T2⟧", ""), "1 manquant"),
        (lambda t: t + " ⟦T1⟧", "1 dupliqué"),
        (lambda t: t + " ⟦T9⟧", "1 inconnu"),
        (lambda t: t.replace("⟦T1⟧", "[T1]"), "1 manquant"),
    ],
)
def test_marker_must_appear_exactly_once(index: LexiconIndex, transform, message: str) -> None:
    with pytest.raises(TranslationError, match=message):
        translate_protected(TEXT, FakeTranslator(transform), index)


def test_translator_failure_is_wrapped(index: LexiconIndex) -> None:
    def boom(text: str) -> str:
        raise RuntimeError("panne")

    with pytest.raises(TranslationError, match="RuntimeError"):
        translate_protected(TEXT, FakeTranslator(boom), index)


def test_source_with_markers_is_rejected(index: LexiconIndex) -> None:
    with pytest.raises(TranslationError):
        protect_terms("texte ⟦T1⟧", index)
    assert restore_terms("rien", protect_terms("aucun terme", index)) == "rien"
