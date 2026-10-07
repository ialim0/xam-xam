from xamxam.lexicon import LexiconIndex
from xamxam.pipeline import XamXamPipeline
from xamxam.pronounce import PronunciationRewriter


def test_rewrite_replaces_terms_and_keeps_the_rest(index: LexiconIndex) -> None:
    result = PronunciationRewriter(index).rewrite("Hypoténuse bi, triangle rectangle la.")
    assert result.text == "ipoteniws bi, tiriyaangal regtaangal la."
    assert [(r.original, r.term) for r in result.replacements] == [
        ("Hypoténuse", "hypoténuse"),
        ("triangle rectangle", "triangle rectangle"),
    ]


def test_rewrite_without_known_terms_is_identity(index: LexiconIndex) -> None:
    result = PronunciationRewriter(index).rewrite("Nanga def ?")
    assert result.text == "Nanga def ?"
    assert result.replacements == ()


def test_pipeline_normalizes_then_rewrites(pipeline: XamXamPipeline) -> None:
    prepared = pipeline.prepare("Ci benn triangle rectangle, BC² = AB² + AC².")
    assert prepared.normalized == (
        "Ci benn triangle rectangle, bee see au carré égale aa bee au carré plus aa see au carré."
    )
    assert prepared.text == (
        "Ci benn tiriyaangal regtaangal, bee see au carré égale aa bee au carré "
        "plus aa see au carré."
    )


def test_pipeline_rewrites_terms_produced_by_normalization(pipeline: XamXamPipeline) -> None:
    # « // » devient « parallèle à », puis « parallèle » est corrigé par le lexique.
    assert pipeline.prepare("(AB) // (CD)").text == "(aa bee) paralel à (see dee)"


def test_pipeline_normalizes_unicode(pipeline: XamXamPipeline) -> None:
    decomposed = "hypoténuse"  # « é » en forme décomposée (NFD)
    assert pipeline.prepare(decomposed).text == "ipoteniws"
