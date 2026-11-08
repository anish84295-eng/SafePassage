from safepassage.structures.trie import Trie


def test_prefix_case_insensitive_duplicates_and_limit():
    trie = Trie()
    trie.insert("Marine Drive", 1, (18.9, 72.8))
    trie.insert("Marine Drive", 1, (18.9, 72.8))
    trie.insert("Marine Lines", 2, (18.91, 72.81))
    trie.insert("Market Road", 3, (18.92, 72.82))
    assert [entry["node_id"] for entry in trie.search("mArInE")] == [1, 2]
    assert len(trie.search("ma", limit=1)) == 1
    assert trie.search("xyz") == []
