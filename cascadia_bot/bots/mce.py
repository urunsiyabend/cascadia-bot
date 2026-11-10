"""Flat Monte Carlo evaluation (MCE).

Inspired by Gedda et al., "Monte Carlo Methods for the Game Kingdomino"
(2018), where flat Monte Carlo with greedy playouts and a score-difference
reward beat UCT on a similar stochastic tile-drafting game.

For each of the ``top_k`` greedy candidates the bot runs playouts: resample the
hidden information, play the candidate, then let every player follow a greedy
policy for ``horizon`` more of our own turns (0 = to the end of the game) and
evaluate like :class:`MCTSBot` (score + estimated future value). The candidate
with the best mean reward is played.

Defaults come from sweeps against ``heuristic`` (2 players, 160 games each):
horizon 3, 96 playouts, 12 candidates, successive halving and the learned
value model as leaf evaluator (+5.9 points per game, 75% wins, ~10 s per game;
horizon 5 with the hand-written potential: +5.5 at ~15 s). Full-game playouts
were much worse (-0.7 to -4.6 points) because of playout noise.

Budget allocation over candidates (``allocation``):

* ``uniform`` - round robin.
* ``ucb`` - UCB1 (exploration constant ``c`` in points).
* ``halving`` - successive halving: equal budget per round, keep the better
  half of the candidates each round (best-arm identification).

``reward``: ``relative`` (own score minus best opponent, own score in solo),
``own`` (own score only) or ``win`` (estimated probability of finishing ahead of
every opponent; the estimate error grows with the turns left, see
:meth:`MCEBot._win_probability`). ``opponents``: ``greedy`` or ``random`` playout
policy for the other players (random is cheaper; their score is then
meaningless, so it is paired with ``reward=own``).

``crn`` (common random numbers, default on): with ``uniform`` and ``halving``
every candidate is evaluated on the *same* sampled futures (same hidden tile
order, bag order and policy tie-breaks).

Measured noise (standard deviation of the score difference between two good
candidates in one playout): ~2 points with ``horizon=1-2``, ~4-5 with
``horizon=4`` and ~7-10 for full-game playouts, while good candidates differ by
1-5 points. Full playouts therefore need 10-15x more samples for the same
precision: decisions diverge chaotically after a different first move, and CRN
does not remove that noise.
"""

from __future__ import annotations

import math
import random
import time

from ..game import Game, Placement
from .mcts import MCTSBot
from .probability import turns_left
from .simple import RandomBot


class MCEBot(MCTSBot):
    name = "mce"

    def __init__(self, seed: int | None = None, playouts: int = 96, time_limit: float = 0.0,
                 top_k: int = 12, allocation: str = "halving", c: float = 4.0, horizon: int = 3,
                 reward: str = "relative", opponents: str = "greedy", potential_weight: float = 1.0,
                 crn: bool = True, evaluator: str = "learned", win_sigma: float = 2.1, **params) -> None:
        super().__init__(seed, iterations=playouts, time_limit=time_limit, top_k=top_k, depth=horizon,
                         c=c, potential_weight=potential_weight, evaluator=evaluator, **params)
        if allocation not in ("uniform", "ucb", "halving"):
            raise ValueError("allocation must be uniform, ucb or halving")
        if reward not in ("relative", "own", "win"):
            raise ValueError("reward must be relative, own or win")
        if opponents not in ("greedy", "random"):
            raise ValueError("opponents must be greedy or random")
        if allocation == "halving" and time_limit > 0:
            raise ValueError("halving needs a fixed playout budget (use ucb with time_limit)")
        self.allocation = allocation
        self.crn = bool(crn) and allocation != "ucb"
        self.horizon = int(horizon)
        self.reward_mode = reward
        self.win_sigma = float(win_sigma)
        self._opponent_policy = (
            RandomBot(seed=self.rng.randrange(2**31)) if opponents == "random" else self._policy
        )

    # ------------------------------------------------------------------ playouts
    def _playout(self, game: Game, placement: Placement, seed: int) -> float:
        me = game.current_player
        sim = game.determinize(random.Random(seed))
        self._policy.rng.seed(seed + 1)
        self._opponent_policy.rng.seed(seed + 2)
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
        if self.reward_mode == "own" or (self.reward_mode == "win" and sim.num_players == 1):
            return self._value(sim, me)
        if self.reward_mode == "win":
            return self._win_probability(sim, me)
        return self._reward(sim, me)

    def _win_probability(self, sim: Game, me: int) -> float:
        """P(our final score beats every opponent's), from estimated final scores.

        The estimate error of a final score difference grows like
        ``win_sigma * sqrt(turns left)`` (measured on ValueBot self-play: 2.25 points
        with 1 turn left, 7.6 with 20). At the end of the game this is exactly
        1 / 0.5 / 0 for win / tie / loss.
        """
        totals = [s.total for s in sim.scores()]
        values = [self._value(sim, p, totals[p]) for p in range(sim.num_players)]
        diff = values[me] - max(v for i, v in enumerate(values) if i != me)
        sigma = self.win_sigma * math.sqrt(max(0, turns_left(sim, me)))
        if sigma <= 1e-9:
            return 1.0 if diff > 0 else 0.5 if diff == 0 else 0.0
        return 0.5 * (1.0 + math.erf(diff / (sigma * math.sqrt(2.0))))

    def choose_placement(self, game: Game) -> Placement:
        cands = self._ranked(game, use_nature=self.use_nature)
        if len(cands) == 1:
            return cands[0].placement
        n = len(cands)
        visits = [0] * n
        totals = [0.0] * n

        def run(i: int, seed: int | None = None) -> None:
            if seed is None:
                seed = self.rng.randrange(2**62)
            totals[i] += self._playout(game, cands[i].placement, seed)
            visits[i] += 1

        def new_seeds(count: int) -> list[int | None]:
            # Shared futures for every candidate (CRN) or independent ones.
            return [self.rng.randrange(2**62) for _ in range(count)] if self.crn else [None] * count

        if self.allocation == "halving":
            alive = list(range(n))
            rounds = max(1, math.ceil(math.log2(n)))
            per_round = self.iterations / rounds
            for _ in range(rounds):
                each = max(1, int(per_round // len(alive)))
                seeds = new_seeds(each)
                for i in alive:
                    for seed in seeds:
                        run(i, seed)
                if len(alive) == 1:
                    break
                alive.sort(key=lambda i: totals[i] / visits[i], reverse=True)
                alive = alive[: max(1, math.ceil(len(alive) / 2))]
            best = alive[0]
        else:
            deadline = time.perf_counter() + self.time_limit if self.time_limit > 0 else None
            k = 0
            seed: int | None = None
            while True:
                if deadline is not None:
                    if k >= n and time.perf_counter() >= deadline:
                        break
                elif k >= self.iterations:
                    break
                if self.allocation == "uniform":
                    i = k % n
                    if i == 0:
                        seed = new_seeds(1)[0]
                elif k < n:
                    i = k
                else:
                    log_k = math.log(k)
                    i = max(range(n), key=lambda j: totals[j] / visits[j] + self.c * math.sqrt(log_k / visits[j]))
                run(i, seed if self.allocation == "uniform" else None)
                k += 1
            best = max(range(n), key=lambda j: (totals[j] / visits[j], visits[j]))

        self.last_stats = {
            "playouts": sum(visits),
            "visits": visits,
            "means": [round(t / v, 2) if v else None for t, v in zip(totals, visits)],
            "chosen_rank": best,
        }
        return cands[best].placement
