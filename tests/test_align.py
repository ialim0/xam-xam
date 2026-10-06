import pytest

from xamxam.eval.align import (
    EditOp,
    TargetTerm,
    align_words,
    check_target_terms,
    count_occurrences,
    tokenize,
    word_error_rate,
)


def test_tokenize() -> None:
    assert tokenize("L'hypoténuse, c'est-à-dire : AB !") == ["l'hypoténuse", "c'est-à-dire", "ab"]


def test_align_identical() -> None:
    alignment = align_words(["a", "b"], ["a", "b"])
    assert [p.op for p in alignment] == [EditOp.EQUAL, EditOp.EQUAL]
    assert word_error_rate(alignment) == 0.0


@pytest.mark.parametrize(
    ("hypothesis", "expected"),
    [
        (["a", "x", "c"], [EditOp.EQUAL, EditOp.SUBSTITUTE, EditOp.EQUAL]),
        (["a", "c"], [EditOp.EQUAL, EditOp.DELETE, EditOp.EQUAL]),
        (["a", "b", "y", "c"], [EditOp.EQUAL, EditOp.EQUAL, EditOp.INSERT, EditOp.EQUAL]),
    ],
)
def test_align_edit_types(hypothesis: list[str], expected: list[EditOp]) -> None:
    alignment = align_words(["a", "b", "c"], hypothesis)
    assert [p.op for p in alignment] == expected
    assert word_error_rate(alignment) == pytest.approx(1 / 3)


def test_alignment_keeps_words() -> None:
    alignment = align_words(["le", "triangle"], ["le", "trayangle"])
    assert [(p.reference, p.hypothesis) for p in alignment] == [
        ("le", "le"),
        ("triangle", "trayangle"),
    ]


def test_wer_with_empty_reference() -> None:
    assert word_error_rate(align_words([], [])) == 0.0
    assert word_error_rate(align_words([], ["bruit"])) == 1.0


def test_count_occurrences_prefers_longest_form() -> None:
    tokens = tokenize("triangle rectangle et triangle")
    assert count_occurrences(tokens, ["triangle rectangle", "triangle"]) == 2
    assert count_occurrences(tokens, ["triangle rectangle"]) == 1


def test_check_target_terms_accepts_pronunciation() -> None:
    target = TargetTerm(
        term="hypoténuse",
        source_forms=("hypoténuse",),
        accepted_forms=("hypoténuse", "ipoteniws"),
    )
    source = "Hypoténuse bi ak hypoténuse bi"
    [ok] = check_target_terms(source, "ipoteniws bi ak hypoténuse bi", [target])
    assert (ok.occurrences, ok.errors) == (2, 0)
    [missed] = check_target_terms(source, "ipoteniws bi ak haïpoténiouz bi", [target])
    assert (missed.occurrences, missed.errors) == (2, 1)


def test_declared_target_counts_at_least_once() -> None:
    target = TargetTerm("parallèle", ("parallèle",), ("parallèle",))
    [check] = check_target_terms("dañoo parallel", "dañoo parallel", [target])
    assert (check.occurrences, check.errors) == (1, 1)
