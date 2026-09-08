# Benchmark results

Measurements from an AMD Ryzen 5 5600X (6 cores, 12 threads), Python 3.14.3,
on 2026-09-01. Timings include result construction and, for parallel runs,
process startup, serialization, and deterministic reduction.

## Python reference improvements

| Workload | Before | After | Speedup |
|---|---:|---:|---:|
| Permutations, support 3 | 132,321/s | 212,373/s | 1.61x |
| Permutations, support 16 | 35,456/s | 64,129/s | 1.81x |
| Permutations, support 64 | 10,107/s | 18,091/s | 1.79x |
| 10x10 operator terms, support 6 | 134,701 pairs/s | 307,894 pairs/s | 2.29x |
| 30x30 operator terms, support 6 | 145,527 pairs/s | 259,948 pairs/s | 1.79x |
| 100x100 operator terms, support 6 | 152,089 pairs/s | 267,445 pairs/s | 1.76x |

The before measurements used the previous validating construction path and
direct accumulator. Workloads are deterministic but these are development
microbenchmarks, not stable performance contracts.

## Parallel operator multiplication

A dense 600x600-term product in `S_6` combines 360,000 input term pairs into
720 output terms:

| Workers | Time/product | Input pairs/s | Serial-relative |
|---:|---:|---:|---:|
| 1 | 1.535 s | 234,520 | 1.00x |
| 2 | 0.827 s | 435,408 | 1.86x |
| 4 | 0.492 s | 731,689 | 3.12x |

A sparse random 300x300-term `S_8` product produced 36,019 output terms and was
slower with processes: roughly 0.74 s serial versus 1.25-1.28 s with two or
four workers. This confirms that output density and reduction volume must be
part of backend-selection heuristics.

## Cython status

After installing the Python development headers, the extension was built and
passed the shared conformance suite. Fresh side-by-side measurements used
Python 3.14.7 after the system Python update:

| Workload | Python | Cython | Cython-relative |
|---|---:|---:|---:|
| Raw permutations, support 3 | 148,143/s | 109,805/s | 0.74x |
| Raw permutations, support 16 | 42,594/s | 51,434/s | 1.21x |
| Raw permutations, support 64 | 20,419/s | 20,257/s | 0.99x |
| 100x100 operator terms, support 6 | 38.038 ms | 35.832 ms | 1.06x |
| 300x300 operator terms, support 8 | 1.245 s | 1.258 s | 0.99x |
| 600x600 operator terms, support 6 | 1.606 s | 1.617 s | 0.99x |

The initial Cython backend still performed dictionary access, sorting, exact
coefficient arithmetic, and result construction through Python objects. Its
compiled loop alone was therefore not a meaningful operator-level speedup.

## Compact native Cython batch

The next implementation deduplicates input permutations, packs canonical
signed-64-bit items into offset/source/target arrays, performs composition
without the GIL, and falls back per pair for any out-of-range label.

| Workload | Python | Native batch | Native-relative |
|---|---:|---:|---:|
| Raw unique pairs, support 3 | 152,963/s | 138,671/s | 0.91x |
| Raw unique pairs, support 16 | 43,874/s | 43,567/s | 0.99x |
| Raw unique pairs, support 64 | 13,268/s | 12,719/s | 0.96x |
| 100x100 operator terms, support 6 | 37.389 ms | 31.030 ms | 1.20x |
| 600x600 operator terms, support 6 | 1.560 s | 1.433 s | 1.09x |

Packing and reconstructing Python values outweighs native composition for
unique-pair batches. Operator products reuse inputs and benefit from
deduplication, although exact fraction multiplication and accumulation remain
the dominant cost in the dense case. The Cython backend therefore remains
explicit rather than automatically selected.
