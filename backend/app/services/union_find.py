"""Small deterministic disjoint-set implementation for ideal conductors only."""


class UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self._parent.setdefault(item, item)
        root = item
        while root != self._parent[root]:
            root = self._parent[root]
        while item != root:
            parent = self._parent[item]
            self._parent[item] = root
            item = parent
        return root

    def union(self, first: str, second: str) -> None:
        left, right = self.find(first), self.find(second)
        # Lexical roots keep diagnostic IDs stable under edge insertion order.
        if left != right:
            self._parent[max(left, right)] = min(left, right)
