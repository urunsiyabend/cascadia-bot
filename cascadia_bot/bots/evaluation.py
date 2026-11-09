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

from ..board import Board
from ..components import Habitat, Tile, Wildlife
from ..game import Game, Placement
from ..hexgrid import Hex
from ..scoring import ScoringCards, wildlife_total


@dataclass
class Candidate:
    value: float
    placement: Placement
    habitat_gain: float
    token_gain: float


class TokenGainCache:
    """Memoised wildlife score delta of putting ``wildlife`` on ``pos``."""

    def __init__(self, board: Board, cards: ScoringCards):
        self.board = board
        self.cards = cards
        self.base = wildlife_total(board.tokens, cards)
        self._cache: dict[tuple[Wildlife, Hex], int] = {}

    def gain(self, wildlife: Wildlife, pos: Hex) -> int:
        key = (wildlife, pos)
        v = self._cache.get(key)
        if v is None:
            tokens = dict(self.board.tokens)
            tokens[pos] = wildlife
            v = wildlife_total(tokens, self.cards) - self.base
            self._cache[key] = v
        return v


def habitat_gain(board: Board, base: dict[Habitat, int], pos: Hex, tile: Tile, rotation: int) -> int:
    after = board.corridor_sizes_after(pos, tile, rotation)
    return sum(after[h] - base[h] for h in after)


def evaluate_candidates(
    game: Game,
    *,
    use_nature: bool = True,
    nature_value: float = 1.0,
    token_bonus: float = 0.0,
    rng: random.Random | None = None,
) -> list[Candidate]:
    """One best placement per (draft option, tile position), scored by immediate gain.

    ``nature_value`` is the value of one nature token (earned on keystones, spent
    for mixed drafts). ``token_bonus`` is added whenever a token is placed rather
    than returned (encourages building patterns that only pay off later).
    """
    rng = rng or random.Random()
    board = game.board
    cards = game.cards
    gains = TokenGainCache(board, cards)
    base_hab = board.largest_corridors()
    frontier = sorted(board.frontier())
    options = game.draft_options()
    if not use_nature:
        options = [o for o in options if o[0] == o[1]]

    hab_cache: dict[tuple[int, Hex], tuple[int, list[int]]] = {}
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
            key = (tile.id, pos)
            if key not in hab_cache:
                best_h = None
                rots: list[int] = []
                for rot in tile.rotations():
                    g = habitat_gain(board, base_hab, pos, tile, rot)
                    if best_h is None or g > best_h:
                        best_h, rots = g, [rot]
                    elif g == best_h:
                        rots.append(rot)
                hab_cache[key] = (best_h or 0, rots)
            h_gain, rots = hab_cache[key]

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
