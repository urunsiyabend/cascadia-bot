"""One-ply bot driven by the learned value model.

For the ``top_k`` greedy candidates it builds the afterstate (tile and token
placed, nature tokens updated), scores it exactly (including the current
majority standing) and adds ``weight * V(afterstate)``, the model's estimate
of the points still to come. No simulation, so it is as fast as ``heuristic``.
"""

from __future__ import annotations

from ..components import TURNS_PER_PLAYER, Wildlife
from ..game import Game, Placement, PreAction
from ..scoring import score_boards
from .evaluation import best_candidate
from .features import LinearValue, default_model, extract
from .probability import bag_counts, next_turn_availability
from .simple import GreedyBot, HeuristicBot


class ValueBot(GreedyBot):
    name = "value"

    def __init__(self, seed: int | None = None, top_k: int = 12, weight: float = 1.0, model: str = "",
                 **params) -> None:
        super().__init__(seed, **params)
        self.top_k = int(top_k)
        self.weight = float(weight)
        self._model_path = model
        self._models: dict[int, LinearValue] = {}
        self._wiper = HeuristicBot(seed=self.rng.randrange(2**31), nature_wipes=self.nature_wipes,
                                   wipe_samples=self.wipe_samples, wipe_margin=self.wipe_margin)

    def _model(self, n: int) -> LinearValue:
        if n not in self._models:
            model = LinearValue.load(self._model_path) if self._model_path else default_model(n)
            if model is None:
                raise RuntimeError(f"no trained value model for {n} players (run cascadia_bot.train_value)")
            self._models[n] = model
        return self._models[n]

    def choose_pre_action(self, game: Game) -> PreAction | None:
        return self._wiper.choose_pre_action(game)

    def choose_placement(self, game: Game) -> Placement:
        me = game.current_player
        cands = sorted(self.candidates(game), key=lambda c: c.value, reverse=True)[: self.top_k]
        left = TURNS_PER_PLAYER - game.turns_taken[me] - 1
        if left <= 0:
            return best_candidate(cands, self.rng).placement
        model = self._model(game.num_players)
        bag = bag_counts(game)
        total = sum(bag.values()) or 1
        frac = {w: bag[w] / total for w in Wildlife}
        opp = [game.boards[i].largest_corridors() for i in range(game.num_players) if i != me]
        best_v, best = None, cands[0].placement
        for cand in cands:
            p = cand.placement
            board = game.board.copy()
            tile = game.display_tiles[p.tile_slot]
            wildlife = game.display_tokens[p.token_slot]
            assert tile is not None and wildlife is not None
            if p.uses_nature_token:
                board.nature_tokens -= 1
            board.place_tile(p.tile_pos, tile, p.rotation)
            if p.token_pos is not None:
                board.place_token(p.token_pos, wildlife)
            boards = list(game.boards)
            boards[me] = board
            score = score_boards(boards, game.cards, game.habitat_majority)[me].total
            avail = next_turn_availability(game, taken_slot=p.token_slot)
            v = score + self.weight * model.predict(extract(board, game.cards, left, avail, frac, opp))
            if best_v is None or v > best_v + 1e-9:
                best_v, best = v, p
        return best
