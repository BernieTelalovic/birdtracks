# ADR 0001: Permutation representation

Status: accepted

Permutations are immutable finite-support bijections of arbitrary-size signed
Python integers. Fixed points are omitted. Equality, hashing, serialization,
and cycle output derive from source-sorted mapping pairs. Canonical cycles begin
at their smallest label and are ordered by that label.

Multiplication is function composition: `p * q = p ∘ q`, so `q` acts first.
Labels absent from either operand are fixed; operands need not have equal
supports. Thus `(1,2,3) * (2,4) = (1,2,4,3)`, equivalently `(2,4,3,1)`.

A future native backend must coordinate-compress Python labels before entering
native loops and use an unsigned index type for dense positions. It must never
narrow the original labels to C or C++ fixed-width integers.
