"""Flat Monte Carlo evaluation (MCE).

Inspired by Gedda et al., "Monte Carlo Methods for the Game Kingdomino"
(2018), where flat Monte Carlo with greedy playouts and a score-difference
reward beat UCT on a similar stochastic tile-drafting game.

For each of the ``top_k`` greedy candidates the bot runs playouts: resample the
hidden information, play the candidate, then let every player follow a greedy
policy until the end of the game (or for ``horizon`` more of our own turns,
then evaluate like :class:`MCTSBot`). The candidate with the best mean reward
is played.

Budget allocation over candidates (``allocation``):

* ``uniform`` - round robin.
* ``ucb`` - UCB1 (exploration constant ``c`` in points).
* ``halving`` - successive halving: equal budget per round, keep the better
  half of the candidates each round (best-arm identification).

``reward``: ``relative`` (own score minus best opponent, own score in solo) or
``own`` (own score only). ``opponents``: ``greedy`` or ``random`` playout
policy for the other players (random is cheaper; their score is then
meaningless, so it is paired with ``reward=own``).
"""

from __future__ import annotations

import math
import time

from ..game import Game, Placement
from .mcts import MCTSBot
from .simple import RandomBot


class MCEBot(MCTSBot):
    name = "mce"

    def __init__(self, seed: int | None = None, playouts: int = 48, time_limit: float = 0.0,
                 top_k: int = 8, allocation: str = "halving", c: float = 4.0, horizon: int = 0,
                 reward: str = "relative", opponents: str = "greedy", potential_weight: float = 1.0,
                 **params) -> None:
        super().__init__(seed, iterations=playouts, time_limit=time_limit, top_k=top_k, depth=horizon,
                         c=c, potential_weight=potential_weight, **params)
        if allocation not in ("uniform", "ucb", "halving"):
            raise ValueError("allocation must be uniform, ucb or halving")
        if reward not in ("relative", "own"):
            raise ValueError("reward must be relative or own")
        if opponents not in ("greedy", "random"):
            raise ValueError("opponents must be greedy or random")
        if allocation == "halving" and time_limit > 0:
            raise ValueError("halving needs a fixed playout budget (use ucb with time_limit)")
        self.allocation = allocation
        self.horizon = int(horizon)
        self.reward_mode = reward
        self._opponent_policy = (
            RandomBot(seed=self.rng.randrange(2**31)) if opponents == "random" else self._policy
        )

    # ------------------------------------------------------------------ playouts
    def _playout(self, game: Game, placement: Placement) -> float:
        me = game.current_player
        sim = game.determinize(self.rng)
        sim.apply_placement(placement)
        my_moves = 1
        while not sim.game_over:
            if sim.current_player == me:
                if self.horizon and my_moves >= self.horizon:
                    break
                sim.apply_placement(self._policy.choose_placement(sim))
                my_moves += 1
            else:
                sim.apply_placement(self._opponent_policy.choose_placement(sim))
        if self.reward_mode == "own":
            return self._value(sim, me)
        return self._reward(sim, me)

    def choose_placement(self, game: Game) -> Placement:
        cands = self._ranked(game, use_nature=self.use_nature)
        if len(cands) == 1:
            return cands[0].placement
        n = len(cands)
        visits = [0] * n
        totals = [0.0] * n

        def run(i: int) -> None:
            totals[i] += self._playout(game, cands[i].placement)
            visits[i] += 1

        if self.allocation == "halving":
            alive = list(range(n))
            rounds = max(1, math.ceil(math.log2(n)))
            per_round = self.iterations / rounds
            for _ in range(rounds):
                each = max(1, int(per_round // len(alive)))
                for i in alive:
                    for _ in range(each):
                        run(i)
                if len(alive) == 1:
                    break
                alive.sort(key=lambda i: totals[i] / visits[i], reverse=True)
                alive = alive[: max(1, math.ceil(len(alive) / 2))]
            best = alive[0]
        else:
            deadline = time.perf_counter() + self.time_limit if self.time_limit > 0 else None
            k = 0
            while True:
                if deadline is not None:
                    if k >= n and time.perf_counter() >= deadline:
                        break
                elif k >= self.iterations:
                    break
                if k < n:
                    i = k
                elif self.allocation == "uniform":
                    i = k % n
                else:
                    log_k = math.log(k)
                    i = max(range(n), key=lambda j: totals[j] / visits[j] + self.c * math.sqrt(log_k / visits[j]))
                run(i)
                k += 1
            best = max(range(n), key=lambda j: (totals[j] / visits[j], visits[j]))

        self.last_stats = {
            "playouts": sum(visits),
            "visits": visits,
            "means": [round(t / v, 2) if v else None for t, v in zip(totals, visits)],
            "chosen_rank": best,
        }
        return cands[best].placement
