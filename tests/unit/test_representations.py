"""Intentional compatibility with standalone representation algebra."""

import pytest

import birdtracks

from birdtracks import representations


def test_missing_backend_reports_installation(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError("No module named 'pair_multiplication'")

    monkeypatch.setattr(representations, "import_module", missing)
    with pytest.raises(ImportError, match="python -m pip install -e"):
        representations.pair_backend()


@pytest.fixture
def backend():
    try:
        return representations.pair_backend()
    except ImportError as exc:
        pytest.skip(str(exc))


def test_fundamental_square(backend):
    fundamental = backend.YoungDiagram((1,))
    result = representations.tensor_product(fundamental, fundamental)
    expected = backend.DirectSum(
        [backend.YoungDiagram((2,)), backend.YoungDiagram((1, 1))], [1, 1]
    )
    assert result == expected


def test_top_level_pair_is_native_class(backend):
    from birdtracks import Pair

    assert Pair is backend.Pair
    assert birdtracks.Pair is backend.Pair
    assert "Pair" in dir(birdtracks)
    assert birdtracks.Pair(((1,), (1,))) == backend.Pair(((1,), (1,)))


def test_top_level_pair_missing_dependency(monkeypatch):
    def missing():
        raise ImportError("optional backend unavailable")

    monkeypatch.setattr(representations, "pair_backend", missing)
    with pytest.raises(ImportError, match="optional backend unavailable"):
        birdtracks.Pair
    with pytest.raises(AttributeError):
        birdtracks.nonexistent_attribute


def test_barred_orientation_and_repeated_terms(backend):
    adjoint = backend.Pair(((1,), (1,)))
    result = representations.tensor_product(adjoint, adjoint)
    # Equal partitions with distinct N0 thresholds remain separate terms.
    matches = [(int(term.N0), int(m))
               for term, m in zip(result.elements, result.multiplicities)
               if term.partition == adjoint.partition]
    assert sorted(matches) == [(2, 1), (3, 1)]
    barred = backend.YoungDiagram((1,), barred=True)
    ordinary = backend.YoungDiagram((1,))
    expected = backend.DirectSum(
        [backend.Pair(((), ()), inherited_N0=1), adjoint], [1, 1]
    )
    assert representations.tensor_product(barred, ordinary) == expected


def test_zero_and_identity(backend):
    value = backend.YoungDiagram((1,))
    zero = representations.tensor_product(backend.NullDiagram(), value)
    assert type(zero) is backend.NullDiagram
    identity = backend.YoungDiagram(())
    assert representations.tensor_product(identity, value) == backend.DirectSum([value], [1])


@pytest.mark.parametrize("nc", [2, 3])
def test_nc_boundary_and_inherited_n0(backend, nc):
    value = backend.Pair(((1,), (1,)), inherited_N0=3)
    identity = backend.Pair(((), ()))
    product = representations.tensor_product(value, identity)
    assert product == value * identity
    assert list(product.N0) == [3]
    assert representations.tensor_product(value, identity, Nc=nc) == (
        value * identity
    ).evaluate_for_Nc(nc)


def test_rejects_operator_inputs(backend):
    with pytest.raises(TypeError, match="representation values"):
        representations.tensor_product(object(), backend.YoungDiagram((1,)))
