---
name: birdtrack-algebra
description: Design, implement, test, optimize, or document multiplication and canonicalization of birdtrack projection operators in this repository. Use for birdtrack diagrams, projectors, index contractions, loop factors, Young-diagram compatibility, and Python/Cython/C++ backend work; do not use for unrelated Python maintenance.
---

# Birdtrack algebra

Develop the smallest mathematically explicit change that preserves exactness and can be checked independently.

## Establish the contract

Before implementing a new algebraic operation, identify from the request and repository context:

- the diagram/object type and its boundary indices;
- multiplication/composition order;
- coefficient domain and symbolic parameters such as the representation dimension;
- equivalence moves and canonical form;
- normalization convention and expected zero conditions.

If one of these materially changes the answer and cannot be inferred safely, isolate the undecided part or ask the author rather than embedding a convention silently.

## Implementation shape

- Keep a readable Python reference path as the semantic specification.
- Represent algebraic values immutably where practical, with deterministic equality, hashing, ordering, and serialization.
- Separate validation and canonicalization from multiplication. Canonicalize at documented boundaries and avoid hidden repeated normalization in inner loops.
- Keep coefficients exact. Factor symbolic coefficient manipulation away from graph/diagram topology.
- Design a narrow backend interface around data-oriented inputs and outputs. Avoid exposing Cython, C++, NumPy layout, or ownership details in the public algebra API.
- Profile representative workloads before selecting or expanding a compiled backend. Prefer Cython for narrow acceleration of Python-adjacent loops; prefer C++ when the core requires substantial native data structures, algorithms, or standalone reuse. Treat this as a decision criterion, not a predetermined result.

## Verification ladder

Build confidence from cheap local checks upward:

1. Hand-worked base cases, invalid inputs, identity, and zero behavior.
2. Canonicalization idempotence and invariance under supported equivalence moves.
3. Projector identities, including idempotence and orthogonality when applicable.
4. Associativity checks on small generated examples; never infer commutativity merely from representation-ring multiplication.
5. Cross-checks against `pair_multiplication` when forgetting operator structure should reproduce its representation-level decomposition.
6. One shared conformance suite for Python and every compiled backend.
7. Run all code in the venv we have set up.
8. Benchmarks only after semantic equivalence is established.

Use exact comparisons when exact arithmetic is expected. If a numerical oracle is unavoidable, state tolerances and why they are adequate.

## Legacy reference

For compatibility or cross-check work involving the predecessor project, read [references/pair-multiplication.md](references/pair-multiplication.md). Do not load it for changes unrelated to that boundary.

