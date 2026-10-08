from xamxam.audio_feedback import check_math_audio, synthesize_checked
from xamxam.providers import MockSTTProvider, MockTTSProvider
from xamxam.providers.base import ProviderError

SOURCE = "BC² = AB² + AC²"
TEXT = "bee see au carré égale aa bee au carré plus aa see au carré"


def test_stt_letter_abbreviations_are_recognized_as_points() -> None:
    checks = check_math_audio(SOURCE, "bc au carré égale ab au carré plus ac au carré")
    assert sum(check.expected for check in checks) == 8
    assert all(check.missing == 0 for check in checks)


def test_missing_formula_elements_are_detected() -> None:
    checks = check_math_audio(SOURCE, "bc au carré ab plus ac")
    missing = {(check.kind, check.value): check.missing for check in checks if check.missing}
    assert missing == {("carre", "carre"): 2, ("egal", "egal"): 1}


def test_stt_superscript_counts_as_spoken_square() -> None:
    checks = check_math_audio("3² + 4² = 5²", "3² plus 4² égale 5²")
    assert all(check.missing == 0 for check in checks)


def test_self_check_selects_variant_only_when_anchors_improve() -> None:
    tts = MockTTSProvider()
    stt = MockSTTProvider(
        lambda text: (
            "bc au carré égale ab au carré plus ac au carré"
            if "aa-bee" in text
            else "bc au carré égale au carré plus ac au carré"
        )
    )
    result = synthesize_checked(SOURCE, TEXT, tts=tts, stt=stt)
    assert result.text != TEXT
    assert "aa-bee" in result.text
    assert result.baseline_heard == 7
    assert result.final_heard == result.expected == 8


def test_self_check_rejects_regression() -> None:
    tts = MockTTSProvider()
    stt = MockSTTProvider(
        lambda text: (
            "bc au carré égale ab au carré ac au carré"
            if "aa-bee" in text
            else "bc au carré égale au carré plus ac au carré"
        )
    )
    result = synthesize_checked(SOURCE, TEXT, tts=tts, stt=stt)
    assert result.text == TEXT
    assert result.baseline_heard == result.final_heard == 7


def test_self_check_skips_text_without_math() -> None:
    result = synthesize_checked(
        "Naka nga def?", "Naka nga def?", tts=MockTTSProvider(), stt=MockSTTProvider(lambda _: "")
    )
    assert result.trials == 0
    assert result.expected == 0


def test_self_check_keeps_first_audio_when_stt_is_unavailable() -> None:
    def fail(_: str) -> str:
        raise ProviderError("STT indisponible")

    result = synthesize_checked(SOURCE, TEXT, tts=MockTTSProvider(), stt=MockSTTProvider(fail))
    assert result.text == TEXT
    assert result.trials == 0
