"""Deciding when to spend a nature token to wipe display tokens.

A wipe is a gamble: the wiped tokens are replaced by random draws from the
bag. The decision is an expected-value comparison using public information:

    E[best move value after the wipe] - 1  >  best move value now + margin

where the -1 is the nature token spent (worth 1 point at the end, and one
fewer token for later mixed drafts is reflected because the post-wipe
evaluation is done with one nature token less). Redraws are sampled from the
exact bag composition (:func:`bag_counts`). Candidate subsets are "the k
worst display slots" for k = 1..4, ranked by the best move each slot's
tile+token pair offers. The chosen wipe is re-estimated on fresh samples
(``validate``) to remove the selection bias of picking the best of several
noisy estimates.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from ..components import Wildlife
from ..game import Game, NatureWipe
from .evaluation import evaluate_candidates
from .probability import bag_counts

Evaluator = Callable[[Game], list]


def _best(cands) -> float:
    return max(c.value for c in cands)


def choose_nature_wipe(
    game: Game,
    rng: random.Random,
    *,
    samples: int = 8,
    margin: float = 0.5,
    nature_value: float = 1.0,
    eval_kwargs: dict | None = None,
    validate: bool = True,
) -> NatureWipe | None:
    """Return the most profitable NatureWipe, or None if no wipe beats keeping the display."""
    board = game.board
    if board.nature_tokens <= 0 or game.game_over:
        return None
    kw = dict(eval_kwargs or {})
    kw["nature_value"] = nature_value
    cands = evaluate_candidates(game, rng=rng, **kw)
    if not cands:
        return None
    base = _best(cands)

    slots = [i for i, t in enumerate(game.display_tokens) if t is not None]
    slot_value = {}
    for i in slots:
        paired = [c.value for c in cands if c.placement.tile_slot == i and c.placement.token_slot == i]
        slot_value[i] = max(paired, default=float("-inf"))
    order = sorted(slots, key=lambda i: slot_value[i])

    bag = bag_counts(game)
    pool = [w for w in Wildlife for _ in range(bag[w])]

    def estimate(subset: tuple[int, ...]) -> float:
        total = 0.0
        for _ in range(samples):
            sim = game.clone()
            sim.board.nature_tokens -= 1
            for slot, token in zip(subset, rng.sample(pool, len(subset))):
                sim.display_tokens[slot] = token
            total += _best(evaluate_candidates(sim, rng=rng, **kw))
        return total / samples - nature_value - base

    best_gain, best_subset = margin, None
    for k in range(1, len(order) + 1):
        subset = tuple(sorted(order[:k]))
        if len(pool) < k:
            break
        gain = estimate(subset)
        if gain > best_gain:
            best_gain, best_subset = gain, subset
    if best_subset is None:
        return None
    # The maximum of several noisy estimates is biased upwards ("winner's curse"):
    # confirm the chosen wipe with fresh, independent samples.
    if validate and estimate(best_subset) <= margin:
        return None
    return NatureWipe(best_subset)
