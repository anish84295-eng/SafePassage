import random

import pytest

from safepassage.structures.heap import MinHeap


def test_ordering_and_duplicates():
    heap = MinHeap()
    for value in [4, 1, 3, 1, 2]:
        heap.push(value, value)
    assert [heap.pop()[0] for _ in range(5)] == [1, 1, 2, 3, 4]


def test_empty_heap_errors():
    heap = MinHeap()
    with pytest.raises(IndexError):
        heap.pop()
    with pytest.raises(IndexError):
        heap.peek()


def test_interleaved_push_pop_and_helpers():
    heap = MinHeap()
    assert heap.is_empty()
    heap.push(3, "three")
    heap.push(1, "one")
    assert len(heap) == 2
    assert heap.peek() == (1, "one")
    assert heap.pop() == (1, "one")
    heap.push(2, "two")
    assert [heap.pop(), heap.pop()] == [(2, "two"), (3, "three")]
    assert heap.is_empty()


def test_randomized_order_matches_sorted():
    rng = random.Random(17)
    values = [rng.randint(-10000, 10000) for _ in range(1000)]
    heap = MinHeap()
    for value in values:
        heap.push(value, value)
    assert [heap.pop()[0] for _ in values] == sorted(values)
