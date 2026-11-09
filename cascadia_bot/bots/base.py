"""Bot interface.

A bot is asked for decisions on its own turn:

1. :meth:`Bot.choose_pre_action` is called repeatedly; return a
   :class:`~cascadia_bot.game.WipeOverpopulation` or
   :class:`~cascadia_bot.game.NatureWipe` to act, or ``None`` to go on to drafting.
2. :meth:`Bot.choose_placement` returns the :class:`~cascadia_bot.game.Placement`.

Bots receive the live :class:`~cascadia_bot.game.Game`. They must not mutate it
and must not read hidden information (``game.tile_stack`` order, ``game._rng``).
To simulate, use ``game.determinize(rng)`` which returns an independent copy with
the hidden information resampled.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from ..game import Game, Placement, PreAction


class Bot(ABC):
    name: str = "bot"

    def __init__(self, seed: int | None = None, **params) -> None:
        self.rng = random.Random(seed)
        if params:
            raise TypeError(f"{type(self).__name__} got unknown parameters: {sorted(params)}")

    def reset(self, game: Game, player: int) -> None:
        """Called once at the start of every game."""

    def choose_pre_action(self, game: Game) -> PreAction | None:
        return None

    @abstractmethod
    def choose_placement(self, game: Game) -> Placement: ...

    def __repr__(self) -> str:
        return self.name
