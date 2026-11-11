"""Plan-following bot: commit to a strategy, re-plan only when it stops making sense.

A *plan* is a commitment to two focus animals plus the player's currently
largest habitat corridor (the "no plan" option is also a candidate). While a
plan is active, moves are chosen by the greedy evaluation plus a plan bonus:

* ``k_token``  for placing a token of a focus animal,
* ``k_spot``   for keeping a new tile that accepts a focus animal free,
* ``-k_block`` for putting a non-focus token on a tile that could host a focus animal,
* ``k_habitat`` per tile the focus corridor grows.

Plan selection and re-planning: the expected final score of following each
candidate plan is estimated by Monte Carlo rollouts from the current state
(hidden information resampled, opponents greedy, same seeds for every plan).
Every ``check_every`` own turns the estimates are refreshed. ``replan``:

* ``ev`` (default) - switch only when an alternative's expected score beats the
  current plan by more than ``min_gap`` points AND by ``z`` standard errors of
  the difference, i.e. when continuing is statistically worse, not merely
  when the draws make the plan impossible;
* ``always`` - always take the plan with the best estimate (no commitment);
* ``never``  - keep the plan chosen on the first turn.
"""

from __future__ import annotations

import math
import random
import statistics
from itertools import combinations

from ..components import Habitat, Wildlife
from ..game import Game, Placement
from .evaluation import Candidate, best_candidate, evaluate_candidates
from .simple import GreedyBot

Plan = frozenset  # frozenset of focus Wildlife; empty = no plan

ALL_PLANS: tuple[Plan, ...] = (frozenset(),) + tuple(frozenset(p) for p in combinations(Wildlife, 2))


def plan_name(plan: Plan) -> str:
    return "+".join(sorted(w.name.lower() for w in plan)) if plan else "none"


class PlanBot(GreedyBot):
    name = "plan"

    def __init__(self, seed: int | None = None, replan: str = "ev", samples: int = 6, check_every: int = 3,
                 z: float = 2.0, min_gap: float = 1.0, k_token: float = 1.5, k_spot: float = 0.5,
                 k_block: float = 1.0, k_habitat: float = 0.5, **params) -> None:
        super().__init__(seed, **params)
        if replan not in ("ev", "always", "never"):
            raise ValueError("replan must be ev, always or never")
        self.replan = replan
        self.samples = int(samples)
        self.check_every = int(check_every)
        self.z = float(z)
        self.min_gap = float(min_gap)
        self.k = (float(k_token), float(k_spot), float(k_block), float(k_habitat))
        self._opponent = GreedyBot(seed=self.rng.randrange(2**31), use_nature=False)
        self._rollout_rng = random.Random(self.rng.randrange(2**31))
        self.plan: Plan | None = None
        self.plan_log: list[tuple[int, str]] = []
        self.switches = 0
        self.sim_decisions = 0  # placements simulated in rollouts (compute budget unit)
        self.evaluations = 0  # number of plan (re-)evaluations

    def reset(self, game: Game, player: int) -> None:
        self.plan = None
        self.plan_log = []
        self.switches = 0
        self.sim_decisions = 0
        self.evaluations = 0

    def stats(self) -> dict:
        """Per-game statistics, recorded by the arena / sweep tools."""
        return {
            "switches": self.switches,
            "plan_log": self.plan_log,
            "sim_decisions": self.sim_decisions,
            "evaluations": self.evaluations,
        }

    # ------------------------------------------------------------------ plan policy
    def _bonus(self, game: Game, cand: Candidate, plan: Plan, focus_habitat: Habitat) -> float:
        if not plan:
            return 0.0
        k_token, k_spot, k_block, k_habitat = self.k
        p = cand.placement
        tile = game.display_tiles[p.tile_slot]
        wildlife = game.display_tokens[p.token_slot]
        assert tile is not None and wildlife is not None
        bonus = 0.0
        if p.token_pos is not None:
            if wildlife in plan:
                bonus += k_token
            else:
                host = tile if p.token_pos == p.tile_pos else game.board.tiles[p.token_pos].tile
                if host.wildlife & plan:
                    bonus -= k_block
        if tile.wildlife & plan and p.token_pos != p.tile_pos:
            bonus += k_spot
        if focus_habitat in tile.habitats:
            board = game.board
            after = board.probe().sizes_after(p.tile_pos, tile, p.rotation)[focus_habitat]
            bonus += k_habitat * (after - board.largest_corridor(focus_habitat))
        return bonus

    def _plan_move(self, game: Game, plan: Plan, use_nature: bool, rng: random.Random) -> Placement:
        cands = evaluate_candidates(
            game,
            use_nature=use_nature,
            nature_value=self.nature_value,
            token_bonus=self.token_bonus,
            majority_weight=self.majority_weight,
            majority_ramp=self.majority_ramp,
            rng=rng,
        )
        if not plan:
            return best_candidate(cands, rng).placement
        corridors = game.board.largest_corridors()
        focus = max(Habitat, key=lambda h: corridors[h])
        return max(cands, key=lambda c: c.value + self._bonus(game, c, plan, focus)).placement

    # ------------------------------------------------------------------ evaluation
    def _rollout(self, game: Game, plan: Plan, seed: int) -> float:
        me = game.current_player
        rng = random.Random(seed)
        sim = game.determinize(rng)
        self._opponent.rng.seed(seed + 1)
        while not sim.game_over:
            if sim.current_player == me:
                sim.apply_placement(self._plan_move(sim, plan, False, rng))
            else:
                sim.apply_placement(self._opponent.choose_placement(sim))
            self.sim_decisions += 1
        return float(sim.scores()[me].total)

    def _estimates(self, game: Game) -> dict[Plan, tuple[float, float]]:
        seeds = [self._rollout_rng.randrange(2**62) for _ in range(self.samples)]
        out = {}
        for plan in ALL_PLANS:
            vals = [self._rollout(game, plan, s) for s in seeds]
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            out[plan] = (statistics.fmean(vals), sd / math.sqrt(len(vals)))
        return out

    def _update_plan(self, game: Game) -> None:
        turn = game.turns_taken[game.current_player]
        if self.plan is not None:
            if self.replan == "never" or turn % self.check_every != 0:
                return
        est = self._estimates(game)
        self.evaluations += 1
        best = max(est, key=lambda p: est[p][0])
        if self.plan is None:
            self.plan = best
            self.plan_log.append((turn, plan_name(best)))
            return
        if best == self.plan:
            return
        cur_mean, cur_se = est[self.plan]
        best_mean, best_se = est[best]
        gap = best_mean - cur_mean
        if self.replan == "always" or (gap > self.min_gap and gap > self.z * math.hypot(cur_se, best_se)):
            self.plan = best
            self.switches += 1
            self.plan_log.append((turn, plan_name(best)))

    def choose_placement(self, game: Game) -> Placement:
        if game.turns_taken[game.current_player] < 19:  # no future left to plan for on the last turn
            self._update_plan(game)
        return self._plan_move(game, self.plan or frozenset(), self.use_nature, self.rng)
