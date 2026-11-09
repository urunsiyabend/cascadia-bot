"""Run a single game between bots."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .game import Game, GameConfig
from .scoring import ScoreBreakdown

MAX_PRE_ACTIONS_PER_TURN = 64


@dataclass
class GameResult:
    seed: int | None
    cards: str
    bot_names: list[str]
    scores: list[ScoreBreakdown]
    winners: list[int]
    game: Game
    decision_seconds: list[float] = field(default_factory=list)

    @property
    def totals(self) -> list[int]:
        return [s.total for s in self.scores]


def play_game(
    bots: Sequence,
    config: GameConfig | None = None,
    *,
    on_turn: Callable[[Game], None] | None = None,
) -> GameResult:
    """Play a full game; ``bots[i]`` controls seat ``i`` (seat 0 starts)."""
    config = config or GameConfig(num_players=len(bots))
    if config.num_players != len(bots):
        raise ValueError("number of bots must equal num_players")
    game = Game(config)
    for i, bot in enumerate(bots):
        bot.reset(game, i)
    spent = [0.0] * len(bots)
    while not game.game_over:
        seat = game.current_player
        bot = bots[seat]
        t0 = time.perf_counter()
        for _ in range(MAX_PRE_ACTIONS_PER_TURN):
            action = bot.choose_pre_action(game)
            if action is None:
                break
            game.apply_pre_action(action)
        placement = bot.choose_placement(game)
        spent[seat] += time.perf_counter() - t0
        game.apply_placement(placement)
        if on_turn is not None:
            on_turn(game)
    return GameResult(
        seed=config.seed,
        cards=str(game.cards),
        bot_names=[getattr(b, "label", b.name) for b in bots],
        scores=game.scores(),
        winners=game.winners(),
        game=game,
        decision_seconds=spent,
    )
