# Benchmarks

Run from the repository root:

```sh
PYTHONPATH=src python benchmarks/bench_permutations.py --count 10000 --support 16
PYTHONPATH=src python benchmarks/bench_permutations.py --count 10000 --support 16 --backend cython
PYTHONPATH=src python benchmarks/bench_permutations.py --count 10000 --support 16 --workers 4
python benchmarks/bench_operators.py --terms 100 --support 8
python benchmarks/bench_operators.py --terms 100 --support 8 --workers 4
```

The generator seed is fixed. Record hardware, Python version, count, support,
and worker count when comparing backend changes. Process startup and transport
costs are intentionally included in parallel batch measurements.

## Optional Cython backend

The base install does not require a compiler. To build the optional backend in
a development environment that already has a C compiler and Python headers:

```sh
python -m pip install "Cython>=3,<4" "setuptools>=68"
python -m pip install -e . --no-build-isolation
python benchmarks/bench_operators.py --backend cython
```

Generated C and compiled extension files stay in ignored build locations and
are not source artifacts.
