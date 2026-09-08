"""Tests for formal sums of independent projector diagrams."""

from fractions import Fraction

import pytest

from birdtracks import (
    Antisymmetriser,
    DimensionPolynomial,
    Permutation,
    PermutationSum,
    Projector,
    ProjectorSum,
    PolynomialPermutationSum,
    Symmetriser,
)


def test_projectors_with_unrelated_supports_form_a_sum_without_connections() -> None:
    p = Projector([Symmetriser({1, 2})])
    q = Projector([Antisymmetriser({7, 9})])

    result = p + q - p

    assert isinstance(result, ProjectorSum)
    assert len(result) == 1
    assert result.coefficient(q) == 1


def test_projector_sum_configure_displays_exact_prefactors_and_signs() -> None:
    pytest.importorskip("anywidget")
    p = Projector([Symmetriser((1, 2))])
    q = Projector([Antisymmetriser((2, 3))])
    value = Fraction(2, 3) * p - Fraction(5, 7) * q

    widget = value.evaluate()

    assert widget.projector_sum == value  # type: ignore[attr-defined]
    assert widget.current_projector_sum == value  # type: ignore[attr-defined]
    assert widget._toolbar.widget_role == "toolbar"  # type: ignore[attr-defined]
    assert all(
        editor.group_id == widget._toolbar.group_id
        for editor in widget._term_editors  # type: ignore[attr-defined]
    )
    assert widget._save_step_button.description == "Save"  # type: ignore[attr-defined]
    widget._save_step_button.click()  # type: ignore[attr-defined]
    assert widget._save_step_button.description == "Saving…"  # type: ignore[attr-defined]
    for editor in widget._term_editors:  # type: ignore[attr-defined]
        editor.saved_revision = editor.save_command  # type: ignore[attr-defined]
    assert widget._save_step_button.description == "Saved"  # type: ignore[attr-defined]
    assert len(widget._term_editors) == 2  # type: ignore[attr-defined]
    displayed = {
        (
            editor.graph["coefficient"]["numerator"],
            editor.graph["coefficient"]["denominator"],
        )
        for editor in widget._term_editors  # type: ignore[attr-defined]
    }
    assert displayed == {("2", "3"), ("5", "7")}
    for index, ((projector, coefficient), editor) in enumerate(
        zip(value, widget._term_editors, strict=True)  # type: ignore[attr-defined]
    ):
        signed_term = coefficient * projector
        expected_sign = "-" if signed_term.coefficient < 0 else "+" if index else ""
        assert editor.graph["term_sign"] == expected_sign
    assert all(
        editor.layout.flex == "0 0 auto"
        for editor in widget._term_editors  # type: ignore[attr-defined]
    )


def test_zero_projector_sum_configure_displays_zero() -> None:
    pytest.importorskip("anywidget")

    widget = ProjectorSum().evaluate()

    assert widget.projector_sum == ProjectorSum()  # type: ignore[attr-defined]
    assert len(widget.children) == 3  # type: ignore[attr-defined]
    assert (  # type: ignore[attr-defined]
        widget.children[1].children[0].value
        == '<span class="birdtracks-zero" role="img" aria-label="zero">0</span>'
    )
    assert widget.children[2].description == "Save"  # type: ignore[attr-defined]


def test_widget_removes_terms_with_double_s_a_connections() -> None:
    pytest.importorskip("anywidget")
    vanishing = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((1, 2))]
    )
    surviving = Projector([Symmetriser((2, 3))])

    widget = (vanishing + surviving).evaluate()

    assert widget.projector_sum == ProjectorSum((surviving,))  # type: ignore[attr-defined]
    assert widget.current_projector_sum == ProjectorSum((surviving,))  # type: ignore[attr-defined]


def test_equal_projector_coefficients_are_collected_exactly() -> None:
    p = Projector([Symmetriser({1, 2})])

    result = p + Fraction(2, 3) * p - Fraction(1, 2) * p

    assert result.coefficient(p) == Fraction(7, 6)


def test_collapse_distributes_over_a_projector_sum() -> None:
    p = Projector([Symmetriser({1, 2})])
    q = Projector([Antisymmetriser({2, 3})])

    assert (p + 2 * q).collapse() == p.collapse() + 2 * q.collapse()


def test_symbolic_collapse_combines_polynomial_and_untraced_terms() -> None:
    traced = Projector([Symmetriser({1})]).trace()
    open_projector = Projector([Symmetriser({2})])

    result = (traced + open_projector).collapse()

    assert isinstance(result, PolynomialPermutationSum)
    assert result.coefficient(Permutation.identity()) == DimensionPolynomial(
        {0: 1, 1: 1}
    )


def test_trace_distributes_over_projector_sum() -> None:
    p = Projector([Symmetriser({1, 2})])
    q = Projector([Antisymmetriser({3})])

    traced = (p - 2 * q).trace()

    assert traced == p.trace() - 2 * q.trace()
    assert traced.collapse(dimension=4) == (
        p.trace().collapse(dimension=4) - 2 * q.trace().collapse(dimension=4)
    )


def test_empty_projector_sum_collapses_to_zero() -> None:
    assert ProjectorSum().collapse() == PermutationSum.zero()
