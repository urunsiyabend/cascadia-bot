"""End-game scoring: wildlife scoring cards, habitat corridors, majorities, nature tokens.

Rule references: base-game rulebook (pp. 8-11) plus the designer's published
clarifications (BoardGameGeek / rules FAQ). Interpretations that are not printed
in the rulebook are documented next to the relevant card.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Iterable, Mapping

from .components import Habitat, Wildlife
from .hexgrid import AXES, Hex, connected_components, neighbors

Tokens = Mapping[Hex, Wildlife]


def _table(values: list[int]) -> Callable[[int], int]:
    """Score lookup where values past the end repeat the last entry ("N+")."""

    def lookup(n: int) -> int:
        if n <= 0:
            return 0
        return values[min(n, len(values) - 1)]

    return lookup


# --------------------------------------------------------------------------- utils


def _positions(tokens: Tokens, wildlife: Wildlife) -> set[Hex]:
    return {p for p, w in tokens.items() if w == wildlife}


def max_weight_packing(cells: Iterable[Hex], shapes: Iterable[tuple[frozenset[Hex], int]]) -> int:
    """Best total value of pairwise-disjoint shapes covering a subset of ``cells``.

    Used for elk formations (each elk scores in at most one formation) and for
    pair matchings (hawk D, fox D). Cells not covered by any chosen shape score 0.
    """
    cell_list = sorted(set(cells))
    if not cell_list:
        return 0
    index = {c: i for i, c in enumerate(cell_list)}
    shape_masks: list[tuple[int, int]] = []
    for shape, value in shapes:
        if value <= 0 or not shape:
            continue
        mask = 0
        for c in shape:
            mask |= 1 << index[c]
        shape_masks.append((mask, value))

    # Split into independent components (cells linked through some shape).
    parent = list(range(len(cell_list)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for mask, _ in shape_masks:
        bits = [i for i in range(len(cell_list)) if mask >> i & 1]
        for b in bits[1:]:
            ra, rb = find(bits[0]), find(b)
            if ra != rb:
                parent[ra] = rb

    groups: dict[int, int] = {}
    for i in range(len(cell_list)):
        r = find(i)
        groups[r] = groups.get(r, 0) | (1 << i)

    by_cell: dict[int, list[tuple[int, int]]] = {i: [] for i in range(len(cell_list))}
    for mask, value in shape_masks:
        for i in range(len(cell_list)):
            if mask >> i & 1:
                by_cell[i].append((mask, value))

    memo: dict[int, int] = {}

    def solve(remaining: int) -> int:
        if remaining == 0:
            return 0
        cached = memo.get(remaining)
        if cached is not None:
            return cached
        low = (remaining & -remaining).bit_length() - 1
        rest = remaining & ~(1 << low)
        best = solve(rest)  # leave this cell unscored
        for mask, value in by_cell[low]:
            if mask & remaining == mask:
                v = value + solve(remaining & ~mask)
                if v > best:
                    best = v
        memo[remaining] = best
        return best

    return sum(solve(g) for g in groups.values())


def _sight_lines(hawks: set[Hex]) -> list[tuple[Hex, Hex, list[Hex]]]:
    """Unordered hawk pairs with a line of sight: (a, b, hexes strictly between).

    A line of sight runs flat side to flat side in a straight line and is blocked
    only by another hawk. Adjacent hawks do not form a line of sight with each
    other (designer clarification).
    """
    if len(hawks) < 2:
        return []
    qs = [h[0] for h in hawks]
    rs = [h[1] for h in hawks]
    span = max(max(qs) - min(qs), max(rs) - min(rs)) + 2
    out = []
    for h in hawks:
        for dq, dr in AXES:
            between: list[Hex] = []
            for k in range(1, span + 1):
                cur = (h[0] + dq * k, h[1] + dr * k)
                if cur in hawks:
                    if k >= 2:
                        out.append((h, cur, between))
                    break
                between.append(cur)
    return out


# --------------------------------------------------------------------------- bears

_BEAR_A = _table([0, 4, 11, 19, 27])  # number of pairs, 4+ = 27
_BEAR_C = {1: 2, 2: 5, 3: 8}
_BEAR_D = {2: 5, 3: 8, 4: 13}


def bear_a(tokens: Tokens) -> int:
    """Score by total number of groups of exactly two bears."""
    groups = connected_components(_positions(tokens, Wildlife.BEAR))
    return _BEAR_A(sum(1 for g in groups if len(g) == 2))


def bear_b(tokens: Tokens) -> int:
    """10 points per group of exactly three bears."""
    groups = connected_components(_positions(tokens, Wildlife.BEAR))
    return 10 * sum(1 for g in groups if len(g) == 3)


def bear_c(tokens: Tokens) -> int:
    """Groups of 1/2/3 bears score 2/5/8; +3 per complete set of the three sizes."""
    groups = connected_components(_positions(tokens, Wildlife.BEAR))
    counts = {1: 0, 2: 0, 3: 0}
    for g in groups:
        if len(g) in counts:
            counts[len(g)] += 1
    base = sum(_BEAR_C[s] * n for s, n in counts.items())
    return base + 3 * min(counts.values())


def bear_d(tokens: Tokens) -> int:
    """Groups of 2/3/4 bears score 5/8/13."""
    groups = connected_components(_positions(tokens, Wildlife.BEAR))
    return sum(_BEAR_D.get(len(g), 0) for g in groups)


# --------------------------------------------------------------------------- elk

_ELK_A = [0, 2, 5, 9, 13]  # straight line of 1..4
_ELK_B = {1: 2, 2: 5, 3: 9, 4: 13}  # single, pair, triangle, diamond
_ELK_C = _table([0, 2, 4, 7, 10, 14, 18, 23, 28])  # contiguous group size, 8+ = 28
_ELK_D = [0, 2, 5, 8, 12, 16, 21]  # (partial) ring of 1..6


def _elk_line_shapes(elk: set[Hex]) -> list[tuple[frozenset[Hex], int]]:
    shapes = [(frozenset([e]), _ELK_A[1]) for e in elk]
    for e in elk:
        for dq, dr in AXES:
            line = [e]
            for k in range(1, 4):
                nxt = (e[0] + dq * k, e[1] + dr * k)
                if nxt not in elk:
                    break
                line.append(nxt)
                shapes.append((frozenset(line), _ELK_A[len(line)]))
    return shapes


def elk_a(tokens: Tokens) -> int:
    """Straight lines of 1-4 elk: 2/5/9/13. Longer lines are split optimally."""
    elk = _positions(tokens, Wildlife.ELK)
    return max_weight_packing(elk, _elk_line_shapes(elk))


def _elk_b_shapes(elk: set[Hex]) -> list[tuple[frozenset[Hex], int]]:
    shapes: set[tuple[frozenset[Hex], int]] = set()
    for e in elk:
        shapes.add((frozenset([e]), _ELK_B[1]))
        nbs = neighbors(e)
        for d in range(6):
            a = nbs[d]
            if a not in elk:
                continue
            shapes.add((frozenset([e, a]), _ELK_B[2]))
            b = nbs[(d + 1) % 6]  # common neighbour of e and a
            if b in elk:
                shapes.add((frozenset([e, a, b]), _ELK_B[3]))
                # diamond: e-a edge plus both common neighbours
                c = nbs[(d - 1) % 6]
                if c in elk:
                    shapes.add((frozenset([e, a, b, c]), _ELK_B[4]))
    return list(shapes)


def elk_b(tokens: Tokens) -> int:
    """Exact formations: single 2, pair 5, triangle 9, diamond (rhombus of 4) 13."""
    elk = _positions(tokens, Wildlife.ELK)
    return max_weight_packing(elk, _elk_b_shapes(elk))


def elk_c(tokens: Tokens) -> int:
    """Each contiguous group of elk, any shape: 2,4,7,10,14,18,23,28 (8+)."""
    groups = connected_components(_positions(tokens, Wildlife.ELK))
    return sum(_ELK_C(len(g)) for g in groups)


def _elk_ring_shapes(elk: set[Hex]) -> list[tuple[frozenset[Hex], int]]:
    shapes: set[tuple[frozenset[Hex], int]] = {(frozenset([e]), _ELK_D[1]) for e in elk}
    centers = {n for e in elk for n in neighbors(e)}
    for center in centers:
        ring = [n for n in neighbors(center) if n in elk]
        for k in range(2, len(ring) + 1):
            for combo in combinations(ring, k):
                shapes.add((frozenset(combo), _ELK_D[k]))
    return list(shapes)


def elk_d(tokens: Tokens) -> int:
    """Circular formations: elk around a common centre hex, 1..6 elk = 2,5,8,12,16,21.

    Designer clarification: partial rings may have gaps; they only need to fit in
    a possible ring.
    """
    elk = _positions(tokens, Wildlife.ELK)
    return max_weight_packing(elk, _elk_ring_shapes(elk))


# --------------------------------------------------------------------------- salmon

_SALMON_A = _table([0, 2, 5, 8, 12, 16, 20, 25])  # 7+ = 25
_SALMON_B = _table([0, 2, 4, 9, 11, 17])  # 5+ = 17


def salmon_runs(tokens: Tokens) -> list[set[Hex]]:
    """Runs of salmon.

    A run is a group of adjacent salmon in which every salmon touches at most two
    other salmon. A salmon touching three or more salmon belongs to no run; the
    remaining salmon still form runs (designer clarification).
    """
    salmon = _positions(tokens, Wildlife.SALMON)
    ok = {s for s in salmon if sum(1 for n in neighbors(s) if n in salmon) <= 2}
    return connected_components(ok)


def salmon_a(tokens: Tokens) -> int:
    return sum(_SALMON_A(len(r)) for r in salmon_runs(tokens))


def salmon_b(tokens: Tokens) -> int:
    return sum(_SALMON_B(len(r)) for r in salmon_runs(tokens))


def salmon_c(tokens: Tokens) -> int:
    """Runs of 3 / 4 / 5+ score 10 / 12 / 15; shorter runs score nothing."""
    total = 0
    for r in salmon_runs(tokens):
        n = len(r)
        if n >= 5:
            total += 15
        elif n == 4:
            total += 12
        elif n == 3:
            total += 10
    return total


def salmon_d(tokens: Tokens) -> int:
    """Runs of 3+: 1 point per salmon + 1 per adjacent animal token (any type)."""
    total = 0
    for run in salmon_runs(tokens):
        if len(run) < 3:
            continue
        adjacent = {n for s in run for n in neighbors(s) if n in tokens and n not in run}
        total += len(run) + len(adjacent)
    return total


# --------------------------------------------------------------------------- hawks

_HAWK_A = _table([0, 2, 5, 8, 11, 14, 18, 22, 26])  # 8+ = 26
_HAWK_B = _table([0, 0, 5, 9, 12, 16, 20, 24, 28])  # 8+ = 28 (card starts at 2)
_HAWK_D = _table([0, 4, 7, 9])  # unique animal types between, 3+ = 9


def _isolated_hawks(hawks: set[Hex]) -> set[Hex]:
    return {h for h in hawks if not any(n in hawks for n in neighbors(h))}


def hawk_a(tokens: Tokens) -> int:
    """Hawks not adjacent to any other hawk."""
    return _HAWK_A(len(_isolated_hawks(_positions(tokens, Wildlife.HAWK))))


def hawk_b(tokens: Tokens) -> int:
    """Hawks not adjacent to another hawk AND with line of sight to another hawk.

    Only the scoring hawk must be non-adjacent; its partner may touch other hawks.
    """
    hawks = _positions(tokens, Wildlife.HAWK)
    isolated = _isolated_hawks(hawks)
    seeing: set[Hex] = set()
    for a, b, _ in _sight_lines(hawks):
        seeing.add(a)
        seeing.add(b)
    return _HAWK_B(len(isolated & seeing))


def hawk_c(tokens: Tokens) -> int:
    """3 points per line of sight between two (non-adjacent) hawks."""
    return 3 * len(_sight_lines(_positions(tokens, Wildlife.HAWK)))


def hawk_d(tokens: Tokens) -> int:
    """Pairs of hawks with line of sight; each hawk in at most one pair.

    A pair scores by the number of unique (non-hawk) animal types on the hexes
    between them: 1/2/3+ types = 4/7/9. The best pairing is used.
    """
    hawks = _positions(tokens, Wildlife.HAWK)
    shapes = []
    for a, b, between in _sight_lines(hawks):
        kinds = {tokens[p] for p in between if p in tokens}
        shapes.append((frozenset([a, b]), _HAWK_D(len(kinds))))
    return max_weight_packing(hawks, shapes)


# --------------------------------------------------------------------------- foxes

_FOX_B = _table([0, 3, 5, 7])
_FOX_D = _table([0, 5, 7, 9, 11])


def _adjacent_counts(tokens: Tokens, cells: Iterable[Hex], exclude: set[Hex]) -> dict[Wildlife, int]:
    counts: dict[Wildlife, int] = {}
    seen: set[Hex] = set()
    for c in cells:
        for n in neighbors(c):
            if n in exclude or n in seen:
                continue
            seen.add(n)
            w = tokens.get(n)
            if w is not None:
                counts[w] = counts.get(w, 0) + 1
    return counts


def fox_a(tokens: Tokens) -> int:
    """Per fox: 1 point per unique wildlife type adjacent (other foxes included)."""
    total = 0
    for f in _positions(tokens, Wildlife.FOX):
        total += len({tokens[n] for n in neighbors(f) if n in tokens})
    return total


def fox_b(tokens: Tokens) -> int:
    """Per fox: unique non-fox animal pairs adjacent: 1/2/3 pairs = 3/5/7."""
    total = 0
    for f in _positions(tokens, Wildlife.FOX):
        counts = _adjacent_counts(tokens, [f], {f})
        pairs = sum(1 for w, n in counts.items() if w != Wildlife.FOX and n >= 2)
        total += _FOX_B(pairs)
    return total


def fox_c(tokens: Tokens) -> int:
    """Per fox: number of adjacent animals of the most abundant non-fox type."""
    total = 0
    for f in _positions(tokens, Wildlife.FOX):
        counts = _adjacent_counts(tokens, [f], {f})
        total += max((n for w, n in counts.items() if w != Wildlife.FOX), default=0)
    return total


def fox_d(tokens: Tokens) -> int:
    """Per fox pair: unique non-fox animal pairs among the 8 surrounding hexes.

    1/2/3/4 pairs = 5/7/9/11. Each fox belongs to at most one pair; the best
    pairing is used.
    """
    foxes = _positions(tokens, Wildlife.FOX)
    shapes = []
    for f in foxes:
        for n in neighbors(f):
            if n in foxes and f < n:
                counts = _adjacent_counts(tokens, [f, n], {f, n})
                pairs = sum(1 for w, c in counts.items() if w != Wildlife.FOX and c >= 2)
                shapes.append((frozenset([f, n]), _FOX_D(pairs)))
    return max_weight_packing(foxes, shapes)


# --------------------------------------------------------------------------- variants

_FAMILY = _table([0, 2, 5, 9])  # group size 1/2/3+
_INTERMEDIATE = _table([0, 0, 5, 8, 12])  # group size 2/3/4+


def family_score(tokens: Tokens, wildlife: Wildlife) -> int:
    return sum(_FAMILY(len(g)) for g in connected_components(_positions(tokens, wildlife)))


def intermediate_score(tokens: Tokens, wildlife: Wildlife) -> int:
    return sum(_INTERMEDIATE(len(g)) for g in connected_components(_positions(tokens, wildlife)))


# --------------------------------------------------------------------------- registry

CARD_FUNCTIONS: dict[Wildlife, dict[str, Callable[[Tokens], int]]] = {
    Wildlife.BEAR: {"A": bear_a, "B": bear_b, "C": bear_c, "D": bear_d},
    Wildlife.ELK: {"A": elk_a, "B": elk_b, "C": elk_c, "D": elk_d},
    Wildlife.SALMON: {"A": salmon_a, "B": salmon_b, "C": salmon_c, "D": salmon_d},
    Wildlife.HAWK: {"A": hawk_a, "B": hawk_b, "C": hawk_c, "D": hawk_d},
    Wildlife.FOX: {"A": fox_a, "B": fox_b, "C": fox_c, "D": fox_d},
}

CARD_LETTERS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class ScoringCards:
    """Which wildlife scoring is in use.

    ``mode`` is ``"standard"`` (one A-D card per wildlife), ``"family"`` or
    ``"intermediate"`` (one shared group-size card for every wildlife).
    """

    cards: tuple[str, str, str, str, str] = ("A", "A", "A", "A", "A")
    mode: str = "standard"

    def __post_init__(self) -> None:
        if self.mode not in ("standard", "family", "intermediate"):
            raise ValueError(f"unknown scoring mode {self.mode!r}")
        if len(self.cards) != 5 or any(c not in CARD_LETTERS for c in self.cards):
            raise ValueError(f"cards must be 5 letters A-D, got {self.cards!r}")

    @classmethod
    def from_string(cls, spec: str) -> "ScoringCards":
        """``"AAAAA"``, ``"ABCDA"`` (bear, elk, salmon, hawk, fox), ``"family"``, ``"intermediate"``."""
        s = spec.strip()
        if s.lower() in ("family", "intermediate"):
            return cls(mode=s.lower())
        return cls(cards=tuple(s.upper()))  # type: ignore[arg-type]

    def card(self, wildlife: Wildlife) -> str:
        return self.cards[wildlife]

    def scorer(self, wildlife: Wildlife) -> Callable[[Tokens], int]:
        if self.mode == "family":
            return lambda t: family_score(t, wildlife)
        if self.mode == "intermediate":
            return lambda t: intermediate_score(t, wildlife)
        return CARD_FUNCTIONS[wildlife][self.cards[wildlife]]

    def __str__(self) -> str:
        return self.mode if self.mode != "standard" else "".join(self.cards)


def score_wildlife(tokens: Tokens, cards: ScoringCards) -> dict[Wildlife, int]:
    return {w: cards.scorer(w)(tokens) for w in Wildlife}


def wildlife_total(tokens: Tokens, cards: ScoringCards) -> int:
    return sum(cards.scorer(w)(tokens) for w in Wildlife)


# --------------------------------------------------------------------------- habitats


def majority_bonuses(sizes: list[int]) -> list[int]:
    """Habitat corridor majority bonus for one habitat, given each player's largest corridor.

    * Solo: 2 points if the corridor has 7+ tiles.
    * 2 players: 2 points to the largest; tie -> 1 each; no second place.
    * 3-4 players: largest 3, second 1. Two-way tie for largest: 2 each, no
      second place. Three/four-way tie for largest: 1 each. Tie for second: 0.
    """
    n = len(sizes)
    bonus = [0] * n
    if n == 1:
        return [2 if sizes[0] >= 7 else 0]
    top = max(sizes)
    if top <= 0:
        return bonus
    first = [i for i, s in enumerate(sizes) if s == top]
    if n == 2:
        for i in first:
            bonus[i] = 2 if len(first) == 1 else 1
        return bonus
    if len(first) == 1:
        bonus[first[0]] = 3
        rest = [s for i, s in enumerate(sizes) if i != first[0] and s > 0]
        if rest:
            second_val = max(rest)
            second = [i for i, s in enumerate(sizes) if s == second_val and i != first[0]]
            if len(second) == 1:
                bonus[second[0]] = 1
    elif len(first) == 2:
        for i in first:
            bonus[i] = 2
    else:
        for i in first:
            bonus[i] = 1
    return bonus


@dataclass
class ScoreBreakdown:
    wildlife: dict[Wildlife, int] = field(default_factory=dict)
    habitat: dict[Habitat, int] = field(default_factory=dict)
    habitat_bonus: dict[Habitat, int] = field(default_factory=dict)
    nature_tokens: int = 0

    @property
    def wildlife_total(self) -> int:
        return sum(self.wildlife.values())

    @property
    def habitat_total(self) -> int:
        return sum(self.habitat.values()) + sum(self.habitat_bonus.values())

    @property
    def total(self) -> int:
        return self.wildlife_total + self.habitat_total + self.nature_tokens

    def as_dict(self) -> dict:
        return {
            "wildlife": {w.name.lower(): v for w, v in self.wildlife.items()},
            "habitat": {h.name.lower(): v for h, v in self.habitat.items()},
            "habitat_bonus": {h.name.lower(): v for h, v in self.habitat_bonus.items()},
            "nature_tokens": self.nature_tokens,
            "total": self.total,
        }


def score_boards(boards: list, cards: ScoringCards, habitat_majority: bool = True) -> list[ScoreBreakdown]:
    """Full final scoring for all players (boards are :class:`cascadia_bot.board.Board`)."""
    out = []
    for b in boards:
        out.append(
            ScoreBreakdown(
                wildlife=score_wildlife(b.tokens, cards),
                habitat=b.largest_corridors(),
                habitat_bonus={h: 0 for h in Habitat},
                nature_tokens=b.nature_tokens,
            )
        )
    if habitat_majority:
        for h in Habitat:
            bonuses = majority_bonuses([s.habitat[h] for s in out])
            for s, bonus in zip(out, bonuses):
                s.habitat_bonus[h] = bonus
    return out


__all__ = [
    "ScoringCards",
    "ScoreBreakdown",
    "score_boards",
    "score_wildlife",
    "wildlife_total",
    "majority_bonuses",
    "salmon_runs",
    "max_weight_packing",
    "CARD_FUNCTIONS",
]
