"""Evaluation boundary for Young-diagram / pair-expression values."""

from __future__ import annotations

from birdtracks.pair_evaluation import evaluate
from birdtracks.young_diagrams import PairExpression


class DiagramAlgebraBackend:
    """Evaluate ordered tensor products of exact pair expressions."""

    name = "diagram"

    def validate(self, value: object) -> PairExpression:
        if not isinstance(value, PairExpression):
            raise TypeError("diagram backend expects a PairExpression")
        return value

    def multiply(self, left: PairExpression, right: PairExpression) -> PairExpression:
        if not left.terms or not right.terms:
            return PairExpression(())
        left_syntax = left.syntax or _direct_sum_syntax(len(left.terms))
        right_syntax = right.syntax or _direct_sum_syntax(len(right.terms))
        expression = PairExpression(
            left.terms + right.terms,
            ("(", *left_syntax, ")", "tensor", "(", *right_syntax, ")"),
        )
        return PairExpression.from_state(evaluate(expression)["result"])


def _direct_sum_syntax(term_count: int) -> tuple[str, ...]:
    if term_count == 0:
        return ()
    return tuple(
        token
        for index in range(term_count)
        for token in (("sum", "pair") if index else ("pair",))
    )


diagram_backend = DiagramAlgebraBackend()

__all__ = ["DiagramAlgebraBackend", "diagram_backend"]
