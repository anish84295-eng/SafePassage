"""Disjoint-set union with path compression and union by rank."""

from __future__ import annotations

from typing import Hashable

from safepassage.graph import Graph


class UnionFind:
    """Track disjoint sets of hashable values."""

    def __init__(self, items: list[Hashable]):
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, item: Hashable) -> Hashable:
        """Return a root and compress the traversed parent path."""
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: Hashable, right: Hashable) -> bool:
        """Merge two sets by rank; return whether a merge happened."""
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            return False
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1
        return True

    def components(self) -> list[set[Hashable]]:
        groups: dict[Hashable, set[Hashable]] = {}
        for item in self.parent:
            groups.setdefault(self.find(item), set()).add(item)
        return list(groups.values())


def find_cut_off_nodes(
    graph: Graph, facility_nodes: set[Hashable]
) -> tuple[set[Hashable], list[set[Hashable]]]:
    """Return nodes unable to reach a facility and undirected components."""
    reversed_graph = graph.reversed()
    reachable = set()
    stack = [node for node in facility_nodes if graph.has_node(node)]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(neighbor for neighbor, _weight in reversed_graph.neighbors(node) if neighbor not in reachable)
    union_find = UnionFind(graph.nodes())
    for source in graph.nodes():
        for target, _weight in graph.neighbors(source):
            union_find.union(source, target)
    components = union_find.components()
    return set(graph.nodes()) - reachable, components
