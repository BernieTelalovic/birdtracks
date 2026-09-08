"""Checked compact native batch composition with exact Python fallback."""

from libc.stdint cimport int64_t
from libc.stdlib cimport free, malloc

from birdtracks.permutations.operations import compose
from birdtracks.permutations.types import Permutation


INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1


cdef bint _fits_int64(object permutation):
    cdef object source
    cdef object target
    for source, target in permutation._items:
        if source < INT64_MIN or source > INT64_MAX:
            return False
        if target < INT64_MIN or target > INT64_MAX:
            return False
    return True


cdef inline int64_t _lookup(
    int64_t* sources,
    int64_t* targets,
    Py_ssize_t start,
    Py_ssize_t end,
    int64_t label,
) noexcept nogil:
    cdef Py_ssize_t low = start
    cdef Py_ssize_t high = end
    cdef Py_ssize_t middle
    while low < high:
        middle = low + (high - low) // 2
        if sources[middle] < label:
            low = middle + 1
        else:
            high = middle
    if low < end and sources[low] == label:
        return targets[low]
    return label


cdef void _compose_native_batch(
    Py_ssize_t pair_count,
    Py_ssize_t* permutation_offsets,
    int64_t* sources,
    int64_t* targets,
    Py_ssize_t* left_ids,
    Py_ssize_t* right_ids,
    Py_ssize_t* output_offsets,
    Py_ssize_t* output_counts,
    int64_t* output_sources,
    int64_t* output_targets,
) noexcept nogil:
    cdef Py_ssize_t pair_index
    cdef Py_ssize_t left_start
    cdef Py_ssize_t left_index
    cdef Py_ssize_t left_end
    cdef Py_ssize_t right_index
    cdef Py_ssize_t right_end
    cdef Py_ssize_t output_index
    cdef int64_t source
    cdef int64_t middle
    cdef int64_t target

    for pair_index in range(pair_count):
        left_start = permutation_offsets[left_ids[pair_index]]
        left_index = left_start
        left_end = permutation_offsets[left_ids[pair_index] + 1]
        right_index = permutation_offsets[right_ids[pair_index]]
        right_end = permutation_offsets[right_ids[pair_index] + 1]
        output_index = output_offsets[pair_index]

        while left_index < left_end or right_index < right_end:
            if right_index >= right_end or (
                left_index < left_end
                and sources[left_index] < sources[right_index]
            ):
                source = sources[left_index]
                target = targets[left_index]
                left_index += 1
            elif left_index >= left_end or sources[right_index] < sources[left_index]:
                source = sources[right_index]
                middle = targets[right_index]
                right_index += 1
                target = _lookup(
                    sources, targets, left_start, left_end, middle
                )
            else:
                source = sources[left_index]
                middle = targets[right_index]
                left_index += 1
                right_index += 1
                target = _lookup(
                    sources, targets, left_start, left_end, middle
                )

            if target != source:
                output_sources[output_index] = source
                output_targets[output_index] = target
                output_index += 1

        output_counts[pair_index] = output_index - output_offsets[pair_index]


def multiply_many(object pairs):
    """Compose a deduplicated native batch, falling back without narrowing."""
    cdef Py_ssize_t input_count = len(pairs)
    cdef Py_ssize_t input_index
    cdef Py_ssize_t native_count
    cdef Py_ssize_t native_index
    cdef Py_ssize_t unique_count
    cdef Py_ssize_t unique_index
    cdef Py_ssize_t permutation_total = 0
    cdef Py_ssize_t output_total = 0
    cdef Py_ssize_t position
    cdef Py_ssize_t item_index
    cdef object pair
    cdef object left
    cdef object right
    cdef object permutation
    cdef object identifier
    cdef object fits
    cdef object source
    cdef object target
    cdef list products = [None] * input_count
    cdef list native_indices = []
    cdef list native_left_ids = []
    cdef list native_right_ids = []
    cdef list unique_permutations = []
    cdef list result_items
    cdef dict permutation_ids = {}
    cdef dict fit_cache = {}

    cdef Py_ssize_t* permutation_offsets = NULL
    cdef Py_ssize_t* left_ids = NULL
    cdef Py_ssize_t* right_ids = NULL
    cdef Py_ssize_t* output_offsets = NULL
    cdef Py_ssize_t* output_counts = NULL
    cdef int64_t* sources = NULL
    cdef int64_t* targets = NULL
    cdef int64_t* output_sources = NULL
    cdef int64_t* output_targets = NULL

    for input_index in range(input_count):
        pair = pairs[input_index]
        left = pair[0]
        right = pair[1]
        if not isinstance(left, Permutation) or not isinstance(right, Permutation):
            raise TypeError("compose expects two Permutation objects")
        if not left:
            products[input_index] = right
            continue
        if not right:
            products[input_index] = left
            continue

        fits = fit_cache.get(left)
        if fits is None:
            fits = bool(_fits_int64(left))
            fit_cache[left] = fits
        if fits:
            fits = fit_cache.get(right)
            if fits is None:
                fits = bool(_fits_int64(right))
                fit_cache[right] = fits
        if not fits:
            products[input_index] = compose(left, right)
            continue

        identifier = permutation_ids.get(left)
        if identifier is None:
            identifier = len(unique_permutations)
            permutation_ids[left] = identifier
            unique_permutations.append(left)
            permutation_total += len(left._items)
        native_left_ids.append(identifier)

        identifier = permutation_ids.get(right)
        if identifier is None:
            identifier = len(unique_permutations)
            permutation_ids[right] = identifier
            unique_permutations.append(right)
            permutation_total += len(right._items)
        native_right_ids.append(identifier)
        native_indices.append(input_index)
        output_total += len(left._items) + len(right._items)

    native_count = len(native_indices)
    if native_count == 0:
        return products
    unique_count = len(unique_permutations)

    try:
        permutation_offsets = <Py_ssize_t*>malloc(
            (unique_count + 1) * sizeof(Py_ssize_t)
        )
        left_ids = <Py_ssize_t*>malloc(native_count * sizeof(Py_ssize_t))
        right_ids = <Py_ssize_t*>malloc(native_count * sizeof(Py_ssize_t))
        output_offsets = <Py_ssize_t*>malloc(
            (native_count + 1) * sizeof(Py_ssize_t)
        )
        output_counts = <Py_ssize_t*>malloc(
            native_count * sizeof(Py_ssize_t)
        )
        sources = <int64_t*>malloc(permutation_total * sizeof(int64_t))
        targets = <int64_t*>malloc(permutation_total * sizeof(int64_t))
        output_sources = <int64_t*>malloc(output_total * sizeof(int64_t))
        output_targets = <int64_t*>malloc(output_total * sizeof(int64_t))
        if (
            permutation_offsets == NULL
            or left_ids == NULL
            or right_ids == NULL
            or output_offsets == NULL
            or output_counts == NULL
            or sources == NULL
            or targets == NULL
            or output_sources == NULL
            or output_targets == NULL
        ):
            raise MemoryError("could not allocate native permutation batch")

        position = 0
        permutation_offsets[0] = 0
        for unique_index in range(unique_count):
            permutation = unique_permutations[unique_index]
            for source, target in permutation._items:
                sources[position] = source
                targets[position] = target
                position += 1
            permutation_offsets[unique_index + 1] = position

        output_offsets[0] = 0
        for native_index in range(native_count):
            left_ids[native_index] = native_left_ids[native_index]
            right_ids[native_index] = native_right_ids[native_index]
            output_offsets[native_index + 1] = (
                output_offsets[native_index]
                + permutation_offsets[left_ids[native_index] + 1]
                - permutation_offsets[left_ids[native_index]]
                + permutation_offsets[right_ids[native_index] + 1]
                - permutation_offsets[right_ids[native_index]]
            )

        with nogil:
            _compose_native_batch(
                native_count,
                permutation_offsets,
                sources,
                targets,
                left_ids,
                right_ids,
                output_offsets,
                output_counts,
                output_sources,
                output_targets,
            )

        for native_index in range(native_count):
            position = output_offsets[native_index]
            result_items = [
                (
                    output_sources[position + item_index],
                    output_targets[position + item_index],
                )
                for item_index in range(output_counts[native_index])
            ]
            products[native_indices[native_index]] = (
                Permutation._from_sorted_items(result_items)
            )
    finally:
        free(permutation_offsets)
        free(left_ids)
        free(right_ids)
        free(output_offsets)
        free(output_counts)
        free(sources)
        free(targets)
        free(output_sources)
        free(output_targets)

    return products
