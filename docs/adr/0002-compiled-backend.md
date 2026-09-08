# ADR 0002: Compiled backend

Status: accepted

The Python implementation is the semantic baseline. Independent products can
be process-parallelized through `multiply_many`. Cython is the first compiled
backend because the measured kernel remains closely coupled to Python values
and exact `Fraction` coefficients.

The Cython backend deduplicates eligible input permutations, packs their
canonical sorted items into offset/source/target arrays, and composes the batch
without the GIL. Signed 64-bit labels are accepted only after checking every
source and target. A pair containing any label outside that range is evaluated
by the exact Python reference path before any narrowing conversion occurs.
Public values remain arbitrary-size, readable `Permutation` objects.

This hybrid was chosen over coordinate compression for the first native
implementation because it keeps conversion narrow and independently testable.
Conformance covers both signed-64-bit boundaries, values immediately outside
them, very large Python integers, mixed native/fallback batches, and randomized
products. A future native graph backend may still use coordinate compression.

The compiled backend remains opt-in. Measurements show useful acceleration for
reused operator terms but overhead for batches of unique permutation pairs.
Automatic selection requires representative workload heuristics and is not
part of this decision.
