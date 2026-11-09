"""Monte-Carlo lookahead bot.

For the ``top_k`` greedy candidates it samples ``samples`` determinized futures
(hidden tiles and bag resampled), plays ``depth`` further turns per player with a
fast greedy rollout policy and keeps the candidate with the best mean outcome.

Outcome = own score minus the best opponent's score (own score in solo), using
the full scoring including habitat majorities.
"""

from __future__ import annotations

from ..game import Game, Placement
from .evaluation import relative_score
from .simple import GreedyBot


class LookaheadBot(GreedyBot):
    name = "lookahead"

    def __init__(self, seed: int | None = None, top_k: int = 6, samples: int = 4, depth: int = 1,
                 **params) -> None:
        super().__init__(seed, **params)
        self.top_k = int(top_k)
        self.samples = int(samples)
        self.depth = int(depth)
        self._rollout = GreedyBot(seed=self.rng.randrange(2**31), use_nature=False, token_bonus=0.1)

    def choose_placement(self, game: Game) -> Placement:
        me = game.current_player
        cands = sorted(self.candidates(game), key=lambda c: c.value, reverse=True)
        top = cands[: self.top_k]
        if len(top) == 1:
            return top[0].placement
        best_value, best = None, top[0].placement
        for cand in top:
            total = 0.0
            for _ in range(self.samples):
                sim = game.determinize(self.rng)
                sim.apply_placement(cand.placement)
                turns = self.depth * sim.num_players
                while turns > 0 and not sim.game_over:
                    sim.apply_placement(self._rollout.choose_placement(sim))
                    turns -= 1
                total += relative_score(sim, me)
            mean = total / self.samples + 1e-3 * cand.value  # tie-break on immediate value
            if best_value is None or mean > best_value:
                best_value, best = mean, cand.placement
        return best
