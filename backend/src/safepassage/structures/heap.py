"""A small min-heap of ``(priority, item)`` pairs."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class MinHeap(Generic[T]):
    """A binary min-heap implemented with a Python list."""

    def __init__(self) -> None:
        self._items: list[tuple[float, T]] = []

    def push(self, priority: float, item: T) -> None:
        """Insert an entry in O(log n) time."""
        self._items.append((priority, item))
        index = len(self._items) - 1
        while index > 0:
            parent = (index - 1) // 2
            if self._items[parent] <= self._items[index]:
                break
            self._items[parent], self._items[index] = self._items[index], self._items[parent]
            index = parent

    def pop(self) -> tuple[float, T]:
        """Remove and return the minimum entry in O(log n) time."""
        if not self._items:
            raise IndexError("pop from empty heap")
        minimum = self._items[0]
        last = self._items.pop()
        if self._items:
            self._items[0] = last
            self._sift_down(0)
        return minimum

    def peek(self) -> tuple[float, T]:
        """Return the minimum entry in O(1) time."""
        if not self._items:
            raise IndexError("peek from empty heap")
        return self._items[0]

    def is_empty(self) -> bool:
        """Check whether the heap is empty in O(1) time."""
        return not self._items

    def __len__(self) -> int:
        """Return the entry count in O(1) time."""
        return len(self._items)

    def _sift_down(self, index: int) -> None:
        while True:
            left = 2 * index + 1
            right = left + 1
            smallest = index
            if left < len(self._items) and self._items[left] < self._items[smallest]:
                smallest = left
            if right < len(self._items) and self._items[right] < self._items[smallest]:
                smallest = right
            if smallest == index:
                return
            self._items[index], self._items[smallest] = self._items[smallest], self._items[index]
            index = smallest
