"""Headless Cascadia rules engine and bot test bench."""

from .board import Board
from .components import HABITAT_TILES, STARTER_TILES, Habitat, Tile, Wildlife
from .game import Game, GameConfig, IllegalAction, NatureWipe, Placement, WipeOverpopulation
from .runner import GameResult, play_game
from .scoring import ScoreBreakdown, ScoringCards

__all__ = [
    "Board",
    "Game",
    "GameConfig",
    "GameResult",
    "HABITAT_TILES",
    "STARTER_TILES",
    "Habitat",
    "IllegalAction",
    "NatureWipe",
    "Placement",
    "ScoreBreakdown",
    "ScoringCards",
    "Tile",
    "Wildlife",
    "WipeOverpopulation",
    "play_game",
]
