# Birdtracks repository guidance

## Purpose

This repository extends `BernieTelalovic/pair_multiplication` from multiplication of Young-diagram representation labels to multiplication of birdtrack projection operators. Treat the legacy project as a mathematical reference and source of cross-checks, not as an architecture that must be copied.

## Working agreements

- Ask the author for clarification before choosing or implementing any unspecified approach; never assume a particular implementation. Request pseudocode when it would resolve ambiguity efficiently.
- Minimize token usage. If a requirement is unclear, ask a concise question instead of spending tokens exploring guessed interpretations.
- Clarify the mathematical object, normalization, coefficient domain, and canonical form before fixing a public API around it.
- Keep a clear, typed Python reference implementation. Move measured hot paths behind a narrow backend boundary only after profiling; do not choose Cython or C++ on intuition alone.
- Treat combinatorial performance as a primary design constraint. Structure algorithms, data representations, and work units so independent computations can be parallelized across CPU cores and, where suitable, GPU backends without changing mathematical semantics.
- Prefer exact arithmetic for algebraic identities and coefficients. Any floating-point path must be explicit and tested against exact or high-precision results.
- Make diagram equality and hashing depend on a documented canonical representation. Never rely on incidental construction order, object identity, or unstable hashes.
- Keep immutable algebraic values separate from multiplication algorithms, caches, rendering, and backend-specific storage.
- Reject invalid diagrams and incompatible boundary data at public boundaries with useful errors.
- Preserve deterministic output ordering so results, snapshots, serialization, and benchmarks are reproducible.
- When porting behavior from `pair_multiplication`, add a focused regression test and record whether compatibility is intentional or only a mathematical cross-check.

## Verification

- Test small cases against hand-derived identities and, where applicable, `pair_multiplication` representation decompositions.
- Test algebraic laws appropriate to the implemented object: canonicalization idempotence, projector idempotence/orthogonality, identity and zero behavior, and associativity of multiplication. Do not assume commutativity for operator products.
- Test Python and compiled backends against the same conformance suite.
- Add property-based tests when generators and invariants are stable enough to make failures interpretable.
- Benchmark before and after compiled changes with representative diagram sizes; keep correctness tests separate from performance thresholds.
- Run the smallest relevant tests during iteration and the full configured test, type-check, and lint suite before handing off completed code.

## Dependencies and generated files

- Use `pyproject.toml` as the source of package, build, test, lint, and type-check configuration.
- Keep the base install usable without a compiler when practical; compiled acceleration should have a documented build path and fallback policy.
- Ask before adding a required runtime dependency or committing generated C/C++ sources, benchmark artifacts, or large fixtures.
- Do not edit generated extension sources by hand.

## Documentation

- Define birdtrack notation, index orientation, composition order, loop factors, normalization, and the role of the symbolic dimension parameter before using them implicitly in code.
- Document public APIs and include small executable examples for new algebraic operations.
- Record consequential choices, especially the Cython-versus-C++ backend decision and canonical representation, in short architecture decision records.

## Code review rules

- Flag loss of exactness, nondeterministic canonicalization, mismatched composition order, incorrect free/dummy-index handling, and compiled/Python semantic drift.
- Treat a speedup without equivalence tests and benchmark evidence as incomplete.
