"""Probability estimates from public information.

Everything here is computed from what every player can see: tokens on boards,
in the display, set aside or removed (solo). The bag composition follows
exactly, because each wildlife has 20 tokens in total.
"""

from __future__ import annotations

import math
from collections import Counter

from ..board import Board
from ..components import DISPLAY_SIZE, TOKENS_PER_WILDLIFE, TURNS_PER_PLAYER, Wildlife
from ..game import Game
from ..scoring import ScoringCards
from .evaluation import TokenGainCache


def bag_counts(game: Game) -> dict[Wildlife, int]:
    """Exact number of tokens of each wildlife in the bag (from public information)."""
    visible: Counter[Wildlife] = Counter()
    for b in game.boards:
        visible.update(b.tokens.values())
    visible.update(t for t in game.display_tokens if t is not None)
    visible.update(game.set_aside)
    visible.update(game.removed_tokens)
    return {w: max(0, TOKENS_PER_WILDLIFE - visible[w]) for w in Wildlife}


def next_turn_availability(game: Game, taken_slot: int | None = None) -> dict[Wildlife, float]:
    """P(at least one token of each wildlife is in the display at the mover's next turn).

    Model: after the move, the 3 remaining display tokens plus ``d`` fresh draws
    from the bag (d = one per player turn until our next turn; 2 in solo) form a
    pool from which tokens leave until 4 remain. Expected count of wildlife ``w``
    is ``4 * (remaining_w + d * f_w) / (3 + d)`` with ``f_w`` the bag fraction;
    availability is ``1 - exp(-E_w)`` (Poisson approximation). Overpopulation
    wipes and nature tokens are ignored.
    """
    bag = bag_counts(game)
    total = sum(bag.values())
    remaining: Counter[Wildlife] = Counter(
        t for i, t in enumerate(game.display_tokens) if t is not None and i != taken_slot
    )
    draws = 2 if game.num_players == 1 else game.num_players
    pool = sum(remaining.values()) + draws
    out = {}
    for w in Wildlife:
        frac = bag[w] / total if total else 0.0
        expected = DISPLAY_SIZE * (remaining[w] + draws * frac) / pool
        out[w] = 1.0 - math.exp(-expected)
    return out


def best_token_gains(board: Board, cards: ScoringCards) -> dict[Wildlife, int]:
    """Best wildlife score gain of one more token of each kind on an existing open spot."""
    gains = TokenGainCache(board, cards)
    out = {}
    for w in Wildlife:
        best = 0
        for spot in board.token_spots(w):
            g = gains.gain(w, spot)
            if board.tiles[spot].tile.keystone:
                g += 1  # nature token
            if g > best:
                best = g
        out[w] = best
    return out


def expected_best(gains: dict[Wildlife, int], availability: dict[Wildlife, float]) -> float:
    """E[max gain over the wildlife that turn out to be available] (independence assumed)."""
    total = 0.0
    none_better = 1.0
    for w in sorted(gains, key=lambda k: -gains[k]):
        g = gains[w]
        if g <= 0:
            break
        p = availability[w]
        total += g * p * none_better
        none_better *= 1.0 - p
    return total


def turns_left(game: Game, player: int) -> int:
    return TURNS_PER_PLAYER - game.turns_taken[player]
