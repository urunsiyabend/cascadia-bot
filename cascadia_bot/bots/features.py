"""State features and a linear value model ("how many more points will this player score?").

The model predicts the *future gain* of a player: final score minus current
score (current score includes the current majority standing). It is trained by
regression on self-play positions (see :mod:`cascadia_bot.train_value`), in the
spirit of afterstate value learning (e.g. TD learning of n-tuple networks for
2048), but with hand-written features.

Wildlife features are keyed by the scoring card in use (``bA`` = bear card A,
``sf`` = salmon in the family variant ...), so the same weight vector serves
every card combination: the model learns separate weights per card.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..board import Board
from ..components import TURNS_PER_PLAYER, Habitat, Wildlife
from ..game import Game
from ..scoring import ScoringCards
from .evaluation import TokenGainCache
from .probability import bag_counts, expected_best, next_turn_availability

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def wildlife_key(cards: ScoringCards, wildlife: Wildlife) -> str:
    if cards.mode == "standard":
        return f"{wildlife.letter}{cards.card(wildlife)}"
    return f"{wildlife.letter}{cards.mode[0]}"


def extract(
    board: Board,
    cards: ScoringCards,
    turns_left: int,
    availability: dict[Wildlife, float],
    bag_fraction: dict[Wildlife, float],
    opponent_largest: list[dict[Habitat, int]],
) -> dict[str, float]:
    """Features of one player's environment.

    ``turns_left``: turns this player still plays. ``availability``: P(each
    wildlife is in the display at this player's next turn) (exactly 0/1 if the
    player is to move). ``opponent_largest``: largest corridors of the others.
    """
    t = turns_left / TURNS_PER_PLAYER
    n = board.nature_tokens
    f: dict[str, float] = {"bias": 1.0, "t": t, "t2": t * t, "nat": n, "nat_t": n * t}

    corridors = board._corridors()
    probe = board.probe()
    frontier = board.frontier()
    for h in Habitat:
        _, sizes = corridors[h]
        largest = max(sizes, default=0)
        big = {i for i, s in enumerate(sizes) if s == largest}
        open_edges = 0
        for pos in frontier:
            if any(c in big for _, c in probe._facing(pos)[h]):
                open_edges += 1
        k = f"H{h.letter}"
        f[k + "_open"] = open_edges
        f[k + "_open_t"] = open_edges * t
        f[k + "_L_t"] = largest * t
        if opponent_largest:
            gap = largest - max(o[h] for o in opponent_largest)
            gap = max(-4, min(4, gap))
            f[k + "_gap"] = gap
            f[k + "_gap_t"] = gap * t
            f[k + "_tie"] = 1.0 if gap == 0 else 0.0

    gains = TokenGainCache(board, cards)
    best: dict[Wildlife, int] = {}
    for w in Wildlife:
        key = wildlife_key(cards, w)
        values = []
        for spot in board.token_spots(w):
            g = gains.gain(w, spot)
            if board.tiles[spot].tile.keystone:
                g += 1
            values.append(g)
        values.sort(reverse=True)
        g1 = max(0, values[0]) if values else 0
        g3 = sum(max(0, v) for v in values[:3])
        best[w] = g1
        count = sum(1 for x in board.tokens.values() if x == w)
        f[key + "_n"] = count
        f[key + "_n_t"] = count * t
        f[key + "_open"] = len(values)
        f[key + "_open_t"] = len(values) * t
        f[key + "_g1"] = g1
        f[key + "_g1_t"] = g1 * t
        f[key + "_g3_t"] = g3 * t
        f[key + "_bag_t"] = bag_fraction[w] * t
        f[key + "_avail_g1"] = availability[w] * g1
    eb = expected_best(best, availability)
    f["eb"] = eb
    f["eb_t"] = eb * t
    return f


def game_features(game: Game, player: int) -> dict[str, float]:
    """Features of ``player`` in the current game state."""
    bag = bag_counts(game)
    total = sum(bag.values()) or 1
    frac = {w: bag[w] / total for w in Wildlife}
    if game.current_player == player and not game.game_over:
        avail = {w: (1.0 if w in game.display_tokens else 0.0) for w in Wildlife}
    else:
        avail = next_turn_availability(game)
    opp = [game.boards[i].largest_corridors() for i in range(game.num_players) if i != player]
    left = TURNS_PER_PLAYER - game.turns_taken[player]
    return extract(game.boards[player], game.cards, left, avail, frac, opp)


class LinearValue:
    """Linear model over named features."""

    def __init__(self, weights: dict[str, float], meta: dict | None = None):
        self.weights = weights
        self.meta = meta or {}

    def predict(self, features: dict[str, float]) -> float:
        w = self.weights
        return sum(w.get(k, 0.0) * v for k, v in features.items())

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"meta": self.meta, "weights": self.weights}, indent=1, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> "LinearValue":
        data = json.loads(Path(path).read_text())
        return cls(data["weights"], data.get("meta"))


@lru_cache(maxsize=None)
def default_model(num_players: int) -> LinearValue | None:
    """Bundled model for a player count (None if not trained yet)."""
    path = MODEL_DIR / f"value_{num_players}p.json"
    return LinearValue.load(path) if path.exists() else None
