"""Bot registry.

Bots are created from a spec string ``name[:key=value,key=value]``, e.g.
``greedy``, ``heuristic:potential_weight=0.5`` or ``lookahead:top_k=8,samples=6``.
Add your own bot by subclassing :class:`Bot` and calling :func:`register`.
"""

from __future__ import annotations

from typing import Callable

from .base import Bot
from .lookahead import LookaheadBot
from .mce import MCEBot
from .mcts import MCTSBot
from .simple import GreedyBot, HeuristicBot, RandomBot
from .value import ValueBot

BOT_REGISTRY: dict[str, Callable[..., Bot]] = {}


def register(name: str, factory: Callable[..., Bot]) -> None:
    BOT_REGISTRY[name] = factory


for _cls in (RandomBot, GreedyBot, HeuristicBot, LookaheadBot, MCTSBot, MCEBot, ValueBot):
    register(_cls.name, _cls)


def _parse_value(v: str):
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def make_bot(spec: str, seed: int | None = None) -> Bot:
    name, _, params = spec.partition(":")
    if name not in BOT_REGISTRY:
        raise ValueError(f"unknown bot {name!r}; available: {', '.join(sorted(BOT_REGISTRY))}")
    kwargs = {}
    if params:
        for item in params.split(","):
            k, _, v = item.partition("=")
            kwargs[k.strip()] = _parse_value(v.strip())
    bot = BOT_REGISTRY[name](seed=seed, **kwargs)
    bot.label = spec  # type: ignore[attr-defined]
    return bot


__all__ = [
    "Bot",
    "RandomBot",
    "GreedyBot",
    "HeuristicBot",
    "LookaheadBot",
    "MCTSBot",
    "MCEBot",
    "ValueBot",
    "make_bot",
    "register",
    "BOT_REGISTRY",
]
