"""Case-insensitive prefix index for named roads and places."""

from __future__ import annotations

from typing import Hashable


class _TrieNode:
    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.entries: list[dict[str, object]] = []


class Trie:
    """Store names and associated node coordinates for prefix lookup."""

    def __init__(self) -> None:
        self._root = _TrieNode()

    def insert(self, name: str, node_id: Hashable, coords: tuple[float, float]) -> None:
        """Insert one name/node entry, ignoring an exact duplicate."""
        normalized = name.casefold().strip()
        if not normalized:
            return
        node = self._root
        for char in normalized:
            node = node.children.setdefault(char, _TrieNode())
        entry = {"name": name, "node_id": node_id, "lat": coords[0], "lng": coords[1]}
        if not any(existing["node_id"] == node_id for existing in node.entries):
            node.entries.append(entry)

    def search(self, prefix: str, limit: int = 10) -> list[dict[str, object]]:
        """Return up to limit matching name/node entries."""
        if limit <= 0:
            return []
        node = self._root
        for char in prefix.casefold().strip():
            if char not in node.children:
                return []
            node = node.children[char]
        matches: list[dict[str, object]] = []

        def collect(current: _TrieNode) -> None:
            if len(matches) >= limit:
                return
            matches.extend(current.entries[: limit - len(matches)])
            for char in sorted(current.children):
                collect(current.children[char])
                if len(matches) >= limit:
                    return

        collect(node)
        return matches


def build_name_index(graph, coords: dict[Hashable, tuple[float, float]]) -> Trie:
    """Index each named road against its endpoint graph nodes."""
    trie = Trie()
    for source in graph.nodes():
        for target, _weight, attributes in graph.edge_records(source):
            name = str(attributes.get("name", "")).strip()
            if name:
                if source in coords:
                    trie.insert(name, source, coords[source])
                if target in coords:
                    trie.insert(name, target, coords[target])
    return trie
