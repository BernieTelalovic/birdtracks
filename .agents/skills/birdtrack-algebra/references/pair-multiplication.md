# `pair_multiplication` reference boundary

Upstream: <https://github.com/BernieTelalovic/pair_multiplication>

The predecessor is a Python/Cython package for Young diagrams, barred diagrams, composite diagram pairs, and direct-sum decompositions for SU(N)-style representation calculations.

## Concepts worth preserving or cross-checking

- Public value concepts include `NullDiagram`, `YoungDiagram`, `Pair`, `DirectSum`, and `DimensionDirectSum`.
- A `Pair` consists of barred and unbarred partitions and tracks `Nc` plus the lowest admissible value `N0`.
- Multiplication returns a direct sum with explicit multiplicities and deterministic human/LaTeX representations.
- Pair multiplication is checked by evaluating at admissible `Nc` and comparing with Littlewood-Richardson multiplication.
- The existing compiled surface is Cython and NumPy-oriented, while orchestration and value objects are Python.

## Extension boundary

Birdtrack projector multiplication contains operator-level information that a representation decomposition forgets. Reuse representation labels and decompositions only where their semantics match. In particular:

- do not inherit commutativity of tensor-product decomposition for operator composition;
- make normalization and index orientation explicit;
- distinguish equality of representation content from equality of operators or diagrams;
- use the predecessor as an oracle for the representation-level image of small products, not as the sole oracle for projector coefficients or topology.

When introducing compatibility, capture it in tests with a short explanation of the mathematical map being checked.

