"""Axial hex-grid helpers.

Coordinates are axial ``(q, r)`` tuples.  The six directions are listed in
circular order, so direction ``d`` and ``(d + 3) % 6`` are opposite.  Edge ``d``
of a tile is the edge shared with the neighbour in direction ``d``.
"""

from __future__ import annotations

from functools import lru_cache

Hex = tuple[int, int]

DIRECTIONS: tuple[Hex, ...] = ((0, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1))

#: One representative direction per straight-line axis (the other half are opposites).
AXES: tuple[Hex, ...] = DIRECTIONS[:3]


def opposite(direction: int) -> int:
    return (direction + 3) % 6


def add(a: Hex, b: Hex) -> Hex:
    return (a[0] + b[0], a[1] + b[1])


def step(h: Hex, direction: int, distance: int = 1) -> Hex:
    dq, dr = DIRECTIONS[direction]
    return (h[0] + dq * distance, h[1] + dr * distance)


@lru_cache(maxsize=None)
def neighbors(h: Hex) -> tuple[Hex, ...]:
    q, r = h
    return tuple((q + dq, r + dr) for dq, dr in DIRECTIONS)


def distance(a: Hex, b: Hex) -> int:
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def direction_between(a: Hex, b: Hex) -> int | None:
    """Direction index from ``a`` to adjacent hex ``b`` (or None if not adjacent)."""
    d = (b[0] - a[0], b[1] - a[1])
    try:
        return DIRECTIONS.index(d)
    except ValueError:
        return None


def connected_components(cells: set[Hex] | frozenset[Hex]) -> list[set[Hex]]:
    """Groups of mutually adjacent cells (flood fill)."""
    remaining = set(cells)
    groups: list[set[Hex]] = []
    while remaining:
        start = remaining.pop()
        group = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for n in neighbors(cur):
                if n in remaining:
                    remaining.remove(n)
                    group.add(n)
                    stack.append(n)
        groups.append(group)
    return groups
