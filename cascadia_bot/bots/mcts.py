"""Monte Carlo Tree Search for Cascadia.

Cascadia is stochastic (new tiles/tokens after every turn) with hidden
information (stack order, bag), and a turn has hundreds to thousands of legal
placements. A plain MCTS tree does not work, so this bot combines:

* **Determinization per iteration** - every iteration starts from
  ``game.determinize(rng)``, i.e. hidden information is resampled
  (information-set MCTS style).
* **Open-loop tree with rank-abstracted actions** - below the root the concrete
  moves differ between determinizations (different tiles appear), so a tree
  edge means "play my k-th best move by the greedy ranking". The root edges are
  the real top-k candidates (the root state is identical in every iteration).
* **Progressive widening** - a node with N visits may use only the best
  ``ceil(widen_c * N ** widen_alpha)`` ranked moves.
* **Opponents** play the greedy policy inside simulations (they are chance
  for us).
* **Depth-limited simulation + evaluation** - after ``depth`` of our own turns
  (and the opponents' replies) the position is scored with
  ``score + potential_weight * potential`` for every player, where potential is
  the expected best next token gain (see :mod:`.probability`). The reward is
  our value minus the best opponent's value (our value in solo).
"""

from __future__ import annotations

import math
import time

from ..components import Wildlife
from ..game import Game, Placement, PreAction
from .evaluation import Candidate, evaluate_candidates
from .features import LinearValue, default_model, game_features
from .probability import best_token_gains, expected_best, next_turn_availability, turns_left
from .simple import GreedyBot, HeuristicBot


class _Node:
    __slots__ = ("visits", "child_visits", "child_value", "children")

    def __init__(self) -> None:
        self.visits = 0
        self.child_visits: dict[int, int] = {}
        self.child_value: dict[int, float] = {}
        self.children: dict[int, _Node] = {}

    def child(self, idx: int) -> "_Node":
        node = self.children.get(idx)
        if node is None:
            node = self.children[idx] = _Node()
        return node


class MCTSBot(GreedyBot):
    name = "mcts"

    def __init__(self, seed: int | None = None, iterations: int = 150, time_limit: float = 0.0,
                 top_k: int = 8, depth: int = 2, c: float = 4.0, widen_c: float = 2.0,
                 widen_alpha: float = 0.5, potential_weight: float = 1.0, evaluator: str = "potential",
                 model: str = "", **params) -> None:
        super().__init__(seed, **params)
        if evaluator not in ("potential", "learned"):
            raise ValueError("evaluator must be potential or learned")
        self.evaluator = evaluator
        self._model_path = model
        self._models: dict[int, LinearValue] = {}
        self.iterations = int(iterations)
        self.time_limit = float(time_limit)
        self.top_k = int(top_k)
        self.depth = int(depth)
        self.c = float(c)
        self.widen_c = float(widen_c)
        self.widen_alpha = float(widen_alpha)
        self.potential_weight = float(potential_weight)
        common = dict(majority_weight=self.majority_weight, majority_ramp=self.majority_ramp)
        self._policy = GreedyBot(seed=self.rng.randrange(2**31), use_nature=False, **common)
        self._wiper = HeuristicBot(seed=self.rng.randrange(2**31))
        self.last_stats: dict = {}

    # ------------------------------------------------------------------ helpers
    def choose_pre_action(self, game: Game) -> PreAction | None:
        return self._wiper.choose_pre_action(game)

    def _ranked(self, game: Game, use_nature: bool) -> list[Candidate]:
        cands = evaluate_candidates(
            game,
            use_nature=use_nature,
            nature_value=self.nature_value,
            token_bonus=self.token_bonus,
            majority_weight=self.majority_weight,
            majority_ramp=self.majority_ramp,
            rng=self.rng,
        )
        cands.sort(key=lambda c: c.value, reverse=True)
        return cands[: self.top_k]

    def _select(self, node: _Node, n_children: int) -> int:
        allowed = min(n_children, max(1, math.ceil(self.widen_c * (node.visits + 1) ** self.widen_alpha)))
        for i in range(allowed):  # untried ranks first, best rank first
            if i not in node.child_visits:
                return i
        log_n = math.log(node.visits + 1)
        best_i, best_u = 0, -math.inf
        for i in range(allowed):
            n = node.child_visits[i]
            u = node.child_value[i] / n + self.c * math.sqrt(log_n / n)
            if u > best_u:
                best_i, best_u = i, u
        return best_i

    def _model(self, num_players: int) -> LinearValue | None:
        model = self._models.get(num_players)
        if model is None:
            model = LinearValue.load(self._model_path) if self._model_path else default_model(num_players)
            if model is not None:
                self._models[num_players] = model
        return model

    def _value(self, sim: Game, player: int, score: int | None = None) -> float:
        if score is None:
            score = sim.scores()[player].total
        if sim.game_over or turns_left(sim, player) <= 0:
            return float(score)
        if self.evaluator == "learned":
            model = self._model(sim.num_players)
            if model is not None:
                return score + self.potential_weight * model.predict(game_features(sim, player))
            # no trained model for this player count: fall back to the potential estimate
        if self.potential_weight == 0:
            return float(score)
        gains = best_token_gains(sim.boards[player], sim.cards)
        if sim.current_player == player and not sim.game_over:
            avail = {w: (1.0 if w in sim.display_tokens else 0.0) for w in Wildlife}
        else:
            avail = next_turn_availability(sim)
        return score + self.potential_weight * expected_best(gains, avail)

    def _reward(self, sim: Game, me: int) -> float:
        totals = [s.total for s in sim.scores()]
        values = [self._value(sim, p, totals[p]) for p in range(sim.num_players)]
        if sim.num_players == 1:
            return values[0]
        return values[me] - max(v for i, v in enumerate(values) if i != me)

    # ------------------------------------------------------------------ search
    def choose_placement(self, game: Game) -> Placement:
        me = game.current_player
        root_cands = self._ranked(game, use_nature=self.use_nature)
        if len(root_cands) == 1:
            return root_cands[0].placement
        root = _Node()
        deadline = time.perf_counter() + self.time_limit if self.time_limit > 0 else None
        iterations = 0
        while True:
            if deadline is not None:
                if time.perf_counter() >= deadline and iterations >= len(root_cands):
                    break
            elif iterations >= self.iterations:
                break
            iterations += 1

            sim = game.determinize(self.rng)
            path: list[tuple[_Node, int]] = []
            idx = self._select(root, len(root_cands))
            sim.apply_placement(root_cands[idx].placement)
            path.append((root, idx))
            node = root.child(idx)
            my_moves = 1
            while not sim.game_over:
                if sim.current_player == me:
                    if my_moves >= self.depth:
                        break
                    cands = self._ranked(sim, use_nature=False)
                    i = self._select(node, len(cands))
                    sim.apply_placement(cands[i].placement)
                    path.append((node, i))
                    node = node.child(i)
                    my_moves += 1
                else:
                    sim.apply_placement(self._policy.choose_placement(sim))
            reward = self._reward(sim, me)
            for n, i in path:
                n.visits += 1
                n.child_visits[i] = n.child_visits.get(i, 0) + 1
                n.child_value[i] = n.child_value.get(i, 0.0) + reward

        best = max(root.child_visits, key=lambda i: (root.child_visits[i], root.child_value[i] / root.child_visits[i]))
        self.last_stats = {
            "iterations": iterations,
            "visits": [root.child_visits.get(i, 0) for i in range(len(root_cands))],
            "means": [
                round(root.child_value[i] / root.child_visits[i], 2) if i in root.child_visits else None
                for i in range(len(root_cands))
            ],
            "chosen_rank": best,
        }
        return root_cands[best].placement
