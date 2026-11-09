"""Fast move evaluation shared by the bots.

Key observation used for speed: wildlife scoring depends only on token
positions, and habitat scoring only on tiles. So for one draft option the value
of a placement decomposes into

    habitat gain(position, rotation) + best token gain(token position)

and the token gain for a given hex is the same whatever tile/rotation is placed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..board import Board, CorridorProbe
from ..components import TURNS_PER_PLAYER, Habitat, Tile, Wildlife
from ..game import Game, Placement
from ..hexgrid import Hex, distance, neighbors
from ..scoring import ScoringCards, majority_bonuses, sight_lines


@dataclass
class Candidate:
    value: float
    placement: Placement
    habitat_gain: float
    token_gain: float


class TokenGainCache:
    """Memoised wildlife score delta of putting ``wildlife`` on ``pos``.

    Only the scoring cards a new token can affect are recomputed: the card of
    the placed wildlife, foxes within distance 2 (fox cards look at neighbours,
    fox D at the 8 hexes around a pair), salmon D (adjacent animals) and hawk D
    (animals between hawks).
    """

    def __init__(self, board: Board, cards: ScoringCards):
        self.board = board
        self.cards = cards
        self._scorers = {w: cards.scorer(w) for w in Wildlife}
        self._base = {w: self._scorers[w](board.tokens) for w in Wildlife}
        self.base = sum(self._base.values())
        self._standard = cards.mode == "standard"
        tokens = board.tokens
        self._foxes = [p for p, w in tokens.items() if w == Wildlife.FOX]
        self._salmon = {p for p, w in tokens.items() if w == Wildlife.SALMON}
        self._hawk_between: set[Hex] = set()
        if self._standard and cards.card(Wildlife.HAWK) == "D":
            hawks = {p for p, w in tokens.items() if w == Wildlife.HAWK}
            for _, _, between in sight_lines(hawks):
                self._hawk_between.update(between)
        self._cache: dict[tuple[Wildlife, Hex], int] = {}

    def _affected(self, wildlife: Wildlife, pos: Hex) -> list[Wildlife]:
        kinds = [wildlife]
        if not self._standard:
            return kinds
        if wildlife != Wildlife.FOX and any(distance(pos, f) <= 2 for f in self._foxes):
            kinds.append(Wildlife.FOX)
        if (
            wildlife != Wildlife.SALMON
            and self.cards.card(Wildlife.SALMON) == "D"
            and any(n in self._salmon for n in neighbors(pos))
        ):
            kinds.append(Wildlife.SALMON)
        if wildlife != Wildlife.HAWK and pos in self._hawk_between:
            kinds.append(Wildlife.HAWK)
        return kinds

    def gain(self, wildlife: Wildlife, pos: Hex) -> int:
        key = (wildlife, pos)
        v = self._cache.get(key)
        if v is None:
            tokens = dict(self.board.tokens)
            tokens[pos] = wildlife
            v = 0
            for kind in self._affected(wildlife, pos):
                v += self._scorers[kind](tokens) - self._base[kind]
            self._cache[key] = v
        return v


class MajorityEstimator:
    """Value change of the habitat majority bonuses if the mover's corridors grew to ``after``.

    The comparison uses the opponents' *current* largest corridors. Because those
    will still grow, the estimate can be scaled down early in the game:
    ``factor = weight * (turn / 20)`` when ``ramp`` is on (1.0 on the last turn).

    ``denial`` also values bonus points taken away from opponents (overtaking or
    tying a leader). ``denial_target`` chooses whose losses count:
    ``"mean"`` - average change over all opponents, ``"leader"`` - only the
    opponent currently ahead on total score (for winning, the leader matters).
    """

    def __init__(self, game: Game, weight: float, ramp: bool = True, denial: float = 0.0,
                 denial_target: str = "leader"):
        if denial_target not in ("mean", "leader"):
            raise ValueError("denial_target must be 'mean' or 'leader'")
        self.me = game.current_player
        self.enabled = weight > 0 and game.habitat_majority
        progress = min(1.0, (game.turns_taken[self.me] + 1) / TURNS_PER_PLAYER)
        self.factor = weight * (progress if ramp else 1.0)
        self.denial = denial if game.num_players > 1 else 0.0
        self.sizes: dict[Habitat, list[int]] = {}
        self.base: dict[Habitat, list[int]] = {}
        self.opponents = [i for i in range(game.num_players) if i != self.me]
        self.leader: int | None = None
        if not self.enabled:
            return
        per_player = [b.largest_corridors() for b in game.boards]
        for h in Habitat:
            self.sizes[h] = [c[h] for c in per_player]
            self.base[h] = majority_bonuses(self.sizes[h])
        if self.denial and denial_target == "leader":
            totals = [s.total for s in game.scores()]
            self.leader = max(self.opponents, key=lambda i: totals[i])

    def delta(self, after: dict[Habitat, int]) -> float:
        if not self.enabled:
            return 0.0
        own = 0
        opp = 0.0
        for h, size in after.items():
            if size == self.sizes[h][self.me]:
                continue
            sizes = list(self.sizes[h])
            sizes[self.me] = size
            new = majority_bonuses(sizes)
            base = self.base[h]
            own += new[self.me] - base[self.me]
            if self.denial:
                if self.leader is not None:
                    opp += new[self.leader] - base[self.leader]
                else:
                    opp += sum(new[i] - base[i] for i in self.opponents) / len(self.opponents)
        return self.factor * (own - self.denial * opp)


def habitat_gain(board: Board, base: dict[Habitat, int], pos: Hex, tile: Tile, rotation: int,
                 majority: MajorityEstimator | None = None) -> float:
    after = board.probe().sizes_after(pos, tile, rotation)
    gain: float = sum(after[h] - base[h] for h in after)
    if majority is not None:
        gain += majority.delta(after)
    return gain


def best_habitat_rotations(probe: CorridorProbe, pos: Hex, tile: Tile,
                           majority: MajorityEstimator | None = None) -> tuple[float, list[int]]:
    """Best habitat gain over the tile's rotations at ``pos`` and all rotations reaching it.

    Equivalent to maximising :func:`habitat_gain` over rotations, but uses the
    probe's precomputed arc table (a few list lookups per rotation).
    """
    arcs = probe.arc_sizes(pos)
    largest = probe.largest
    if tile.keystone:
        h = tile.habitats[0]
        size, top = arcs[h][6], largest[h]
        if size <= top:
            return 0.0, [0]
        g = float(size - top)
        if majority is not None:
            g += majority.delta({h: size})
        return g, [0]
    h1, h2 = tile.habitats
    a1, a2 = arcs[h1], arcs[h2]
    top1, top2 = largest[h1], largest[h2]
    best = -1.0
    rots: list[int] = []
    for r in range(6):
        s1 = a1[r]
        s2 = a2[(r + 3) % 6]
        if s1 > top1 or s2 > top2:
            n1 = s1 if s1 > top1 else top1
            n2 = s2 if s2 > top2 else top2
            g = float(n1 - top1 + n2 - top2)
            if majority is not None:
                g += majority.delta({h1: n1, h2: n2})
        else:
            g = 0.0
        if g > best + 1e-9:
            best, rots = g, [r]
        elif g >= best - 1e-9:
            rots.append(r)
    return best, rots


def evaluate_candidates(
    game: Game,
    *,
    use_nature: bool = True,
    nature_value: float = 1.0,
    token_bonus: float = 0.0,
    majority_weight: float = 0.0,
    majority_ramp: bool = True,
    majority_denial: float = 0.0,
    denial_target: str = "leader",
    rng: random.Random | None = None,
) -> list[Candidate]:
    """One best placement per (draft option, tile position), scored by immediate gain.

    ``nature_value`` is the value of one nature token (earned on keystones, spent
    for mixed drafts). ``token_bonus`` is added whenever a token is placed rather
    than returned (encourages building patterns that only pay off later).
    ``majority_weight`` > 0 adds the estimated change in the habitat majority
    bonus (see :class:`MajorityEstimator`); ``majority_denial`` also values bonus
    points taken from opponents.
    """
    rng = rng or random.Random()
    board = game.board
    cards = game.cards
    gains = TokenGainCache(board, cards)
    probe = board.probe()
    majority = (
        MajorityEstimator(game, majority_weight, majority_ramp, majority_denial, denial_target)
        if majority_weight > 0
        else None
    )
    frontier = sorted(board.frontier())
    options = game.draft_options()
    if not use_nature:
        options = [o for o in options if o[0] == o[1]]

    # Habitat gain depends only on the tile's habitats (not its wildlife), so tiles
    # with the same habitat pair share the cache.
    hab_cache: dict[tuple[tuple[Habitat, ...], Hex], tuple[float, list[int]]] = {}
    out: list[Candidate] = []
    for ts, ks in options:
        tile = game.display_tiles[ts]
        wildlife = game.display_tokens[ks]
        assert tile is not None and wildlife is not None
        cost = nature_value if ts != ks else 0.0

        best_existing: tuple[float, Hex | None] = (0.0, None)  # returning the token is worth 0
        ties: list[Hex | None] = [None]
        for spot in board.token_spots(wildlife):
            v = gains.gain(wildlife, spot) + token_bonus
            if board.tiles[spot].tile.keystone:
                v += nature_value
            if v > best_existing[0] + 1e-9:
                best_existing = (v, spot)
                ties = [spot]
            elif abs(v - best_existing[0]) <= 1e-9:
                ties.append(spot)
        existing_value = best_existing[0]
        existing_choice = rng.choice(ties)

        for pos in frontier:
            key = (tile.habitats, pos)
            cached = hab_cache.get(key)
            if cached is None:
                cached = hab_cache[key] = best_habitat_rotations(probe, pos, tile, majority)
            h_gain, rots = cached

            tok_value, tok_pos = existing_value, existing_choice
            if wildlife in tile.wildlife:
                v = gains.gain(wildlife, pos) + token_bonus + (nature_value if tile.keystone else 0.0)
                if v > tok_value + 1e-9 or (abs(v - tok_value) <= 1e-9 and rng.random() < 0.5):
                    tok_value, tok_pos = v, pos
            placement = Placement(ts, ks, pos, rng.choice(rots), tok_pos)
            out.append(Candidate(h_gain + tok_value - cost, placement, h_gain, tok_value))
    return out


def best_candidate(cands: list[Candidate], rng: random.Random) -> Candidate:
    top = max(c.value for c in cands)
    return rng.choice([c for c in cands if c.value >= top - 1e-9])


def relative_score(game: Game, player: int) -> float:
    """Own total minus the best opponent total (own total in solo)."""
    scores = [s.total for s in game.scores()]
    if game.num_players == 1:
        return float(scores[0])
    others = max(s for i, s in enumerate(scores) if i != player)
    return float(scores[player] - others)
