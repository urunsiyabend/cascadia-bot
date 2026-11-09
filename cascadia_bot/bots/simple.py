"""Baseline bots: random, greedy and greedy-with-potential."""

from __future__ import annotations

from ..components import Wildlife
from ..game import Game, Placement, PreAction, WipeOverpopulation
from .base import Bot
from .evaluation import Candidate, TokenGainCache, best_candidate, evaluate_candidates


class RandomBot(Bot):
    """Uniformly random legal moves (always places the token when it can)."""

    name = "random"

    def choose_placement(self, game: Game) -> Placement:
        rng = self.rng
        board = game.board
        ts, ks = rng.choice([o for o in game.draft_options() if o[0] == o[1]] or game.draft_options())
        tile = game.display_tiles[ts]
        wildlife = game.display_tokens[ks]
        assert tile is not None and wildlife is not None
        pos = rng.choice(sorted(board.frontier()))
        rot = rng.choice(tile.rotations())
        spots: list = board.token_spots(wildlife)
        if wildlife in tile.wildlife:
            spots.append(pos)
        token_pos = rng.choice(spots) if spots else None
        return Placement(ts, ks, pos, rot, token_pos)


class GreedyBot(Bot):
    """Maximises the immediate score gain (wildlife + largest corridors + nature tokens).

    Parameters:
        use_nature: allow spending nature tokens on mixed drafts.
        nature_value: points one nature token is worth to the bot.
        token_bonus: small bonus for placing a token instead of returning it.
        majority_weight: weight of the estimated habitat majority bonus change
            (0 = ignore majorities).
        majority_ramp: scale that estimate by game progress (turn / 20), since
            opponents' corridors still grow.
    """

    name = "greedy"

    def __init__(self, seed: int | None = None, use_nature: bool = True, nature_value: float = 1.0,
                 token_bonus: float = 0.1, majority_weight: float = 1.0, majority_ramp: bool = True,
                 **params) -> None:
        super().__init__(seed, **params)
        self.use_nature = bool(use_nature)
        self.nature_value = float(nature_value)
        self.token_bonus = float(token_bonus)
        self.majority_weight = float(majority_weight)
        self.majority_ramp = bool(majority_ramp)

    def candidates(self, game: Game) -> list[Candidate]:
        return evaluate_candidates(
            game,
            use_nature=self.use_nature,
            nature_value=self.nature_value,
            token_bonus=self.token_bonus,
            majority_weight=self.majority_weight,
            majority_ramp=self.majority_ramp,
            rng=self.rng,
        )

    def choose_placement(self, game: Game) -> Placement:
        return best_candidate(self.candidates(game), self.rng).placement


class HeuristicBot(GreedyBot):
    """Greedy, but re-ranks the top candidates by the *option value* they leave behind.

    potential(board) = sum over wildlife of the best score gain one more token of
    that wildlife could make on an open spot. The final value is
    ``immediate + potential_weight * potential``. It also wipes an optional
    overpopulation when none of the three identical tokens is useful.
    """

    name = "heuristic"

    def __init__(self, seed: int | None = None, potential_weight: float = 0.3, top_k: int = 12,
                 **params) -> None:
        super().__init__(seed, **params)
        self.potential_weight = float(potential_weight)
        self.top_k = int(top_k)

    def _potential(self, game: Game, cand: Candidate) -> float:
        p = cand.placement
        board = game.board.copy()
        tile = game.display_tiles[p.tile_slot]
        wildlife = game.display_tokens[p.token_slot]
        assert tile is not None and wildlife is not None
        board.place_tile(p.tile_pos, tile, p.rotation)
        if p.token_pos is not None:
            board.tokens[p.token_pos] = wildlife
        gains = TokenGainCache(board, game.cards)
        total = 0.0
        for w in Wildlife:
            best = 0
            for spot in board.token_spots(w):
                best = max(best, gains.gain(w, spot))
            total += best
        return total

    def choose_pre_action(self, game: Game) -> PreAction | None:
        kind = game.overpopulated_three()
        if kind is None or not game.can_wipe_overpopulation():
            return None
        board = game.board
        gains = TokenGainCache(board, game.cards)
        useful = any(gains.gain(kind, s) > 0 for s in board.token_spots(kind))
        return None if useful else WipeOverpopulation()

    def choose_placement(self, game: Game) -> Placement:
        cands = self.candidates(game)
        cands.sort(key=lambda c: c.value, reverse=True)
        top = cands[: self.top_k]
        scored = [(c.value + self.potential_weight * self._potential(game, c), c) for c in top]
        best = max(v for v, _ in scored)
        return self.rng.choice([c for v, c in scored if v >= best - 1e-9]).placement
