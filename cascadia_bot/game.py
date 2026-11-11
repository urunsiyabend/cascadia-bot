"""Game state and turn flow.

Turn structure (rulebook pp. 6-7):

1. Overpopulation. If all four tokens in the display are the same wildlife they
   are wiped automatically (repeatedly if needed). If exactly three are the same,
   the active player *may* wipe those three - at most once per turn, and also
   after a nature-token wipe has been made.
2. Nature tokens (any number): spend one to wipe any chosen display tokens, or
   spend one to draft any tile together with any token instead of a fixed pair.
   Wiped tokens are set aside and only go back to the bag once all wipes are
   resolved.
3. Place the tile adjacent to the environment (any rotation), then optionally
   place the token on a tile without a token that shows that wildlife (it may be
   the tile just placed). Otherwise the token returns to the bag. A token placed
   on a keystone tile earns a nature token.
4. Refill the empty display slots (no sliding). Solo: first discard the tile and
   token furthest from the draw stacks, slide the rest away, then draw two.

The game ends when the tile stack cannot refill the display at the end of a
turn; every player then has played exactly 20 turns.

Hidden information: the order of the tile stack and of the bag. Bots receive the
real :class:`Game` object and are trusted not to inspect ``tile_stack`` /
``_rng``; for simulations use :meth:`Game.determinize`.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

from .board import Board
from .components import (
    DISPLAY_SIZE,
    HABITAT_TILES,
    NATURE_TOKEN_SUPPLY,
    STARTER_TILES,
    TOKENS_PER_WILDLIFE,
    Tile,
    Wildlife,
    tiles_for_player_count,
)
from .hexgrid import Hex
from .scoring import CARD_LETTERS, ScoreBreakdown, ScoringCards, score_boards

# --------------------------------------------------------------------------- actions


@dataclass(frozen=True)
class WipeOverpopulation:
    """Optional wipe of exactly three identical display tokens (once per turn)."""


@dataclass(frozen=True)
class NatureWipe:
    """Spend a nature token to wipe the tokens in the given display slots."""

    slots: tuple[int, ...]


PreAction = WipeOverpopulation | NatureWipe


@dataclass(frozen=True)
class Placement:
    """Draft and place.

    ``tile_slot``/``token_slot`` are display indices; if they differ a nature
    token is spent. ``token_pos=None`` returns the token to the bag.
    """

    tile_slot: int
    token_slot: int
    tile_pos: Hex
    rotation: int
    token_pos: Hex | None

    @property
    def uses_nature_token(self) -> bool:
        return self.tile_slot != self.token_slot


# --------------------------------------------------------------------------- config


@dataclass
class GameConfig:
    num_players: int = 2
    cards: ScoringCards | None = None  # None -> random A-D card per wildlife
    habitat_majority: bool = True
    seed: int | None = None
    # "random": every draw picks a uniformly random token from the bag.
    # "presorted": the bag is shuffled once at setup and tokens are drawn in that order;
    # returned tokens are reinserted at uniformly random positions. Both give uniformly
    # random draws; "presorted" keeps the token sequence of a seed much more similar
    # across agents that act differently (common random numbers for paired experiments).
    token_order: str = "random"


@dataclass
class TurnRecord:
    player: int
    turn: int
    pre_actions: list[PreAction] = field(default_factory=list)
    placement: Placement | None = None
    tile_code: str = ""
    wildlife: Wildlife | None = None


class IllegalAction(ValueError):
    pass


# --------------------------------------------------------------------------- game


class Game:
    def __init__(self, config: GameConfig | None = None, **kwargs) -> None:
        if config is None:
            config = GameConfig(**kwargs)
        elif kwargs:
            raise TypeError("pass either a GameConfig or keyword arguments")
        n = config.num_players
        if not 1 <= n <= 4:
            raise ValueError("num_players must be 1-4")
        self.config = config
        self.num_players = n
        self._rng = random.Random(config.seed)
        rng = self._rng

        self.cards = config.cards or ScoringCards(cards=tuple(rng.choice(CARD_LETTERS) for _ in range(5)))  # type: ignore[arg-type]
        self.habitat_majority = config.habitat_majority

        starters = rng.sample(range(len(STARTER_TILES)), n)
        self.boards: list[Board] = [Board.with_starter(s) for s in starters]
        self.starter_indices = starters

        tiles = list(HABITAT_TILES)
        rng.shuffle(tiles)
        self.tile_stack: list[Tile] = tiles[: tiles_for_player_count(n)]
        self.bag: list[Wildlife] = [w for w in Wildlife for _ in range(TOKENS_PER_WILDLIFE)]
        # Simulation copies draw from a pre-shuffled bag order (see determinize) so that
        # futures sampled with the same seed stay comparable across candidate moves.
        self.sequential_bag = False
        if config.token_order not in ("random", "presorted"):
            raise ValueError("token_order must be 'random' or 'presorted'")
        if config.token_order == "presorted":
            rng.shuffle(self.bag)
            self.sequential_bag = True
        self.set_aside: list[Wildlife] = []
        self.removed_tokens: list[Wildlife] = []  # solo discards
        self.nature_supply = NATURE_TOKEN_SUPPLY

        self.display_tiles: list[Tile | None] = [self.tile_stack.pop() for _ in range(DISPLAY_SIZE)]
        self.display_tokens: list[Wildlife | None] = [self._draw_token() for _ in range(DISPLAY_SIZE)]

        self.current_player = 0
        self.turn = 0  # total turns taken
        self.turns_taken = [0] * n
        self.game_over = False
        self.overpopulation_wipe_used = False
        self.history: list[TurnRecord] = []
        self.record_history = True
        self._begin_turn()

    # ----------------------------------------------------------------- tokens
    def _draw_token(self) -> Wildlife | None:
        if not self.bag and self.set_aside:
            self._bag_add(self.set_aside)
            self.set_aside.clear()
        if not self.bag:
            return None
        if self.sequential_bag:
            return self.bag.pop()
        i = self._rng.randrange(len(self.bag))
        self.bag[i], self.bag[-1] = self.bag[-1], self.bag[i]
        return self.bag.pop()

    def _bag_add(self, tokens) -> None:
        """Return tokens to the bag (in sequential mode: at random depths of the pre-shuffled order)."""
        if not self.sequential_bag:
            self.bag.extend(tokens)
            return
        for t in tokens:
            self.bag.insert(self._rng.randrange(len(self.bag) + 1), t)

    def _wipe_slots(self, slots: list[int]) -> None:
        for s in slots:
            tok = self.display_tokens[s]
            if tok is not None:
                self.set_aside.append(tok)
            self.display_tokens[s] = None
        for s in slots:  # draw replacements one at a time, in slot order
            self.display_tokens[s] = self._draw_token()

    def _resolve_four_of_a_kind(self) -> None:
        while True:
            toks = self.display_tokens
            if None in toks or len(set(toks)) != 1:
                return
            kind = toks[0]
            if all(t == kind for t in self.bag):
                return  # cannot ever break the overpopulation; stop
            self._wipe_slots(list(range(DISPLAY_SIZE)))

    def _return_set_aside(self) -> None:
        self._bag_add(self.set_aside)
        self.set_aside.clear()

    def _begin_turn(self) -> None:
        self.overpopulation_wipe_used = False
        self._resolve_four_of_a_kind()
        if self.record_history:
            self.history.append(TurnRecord(self.current_player, self.turn))

    # ----------------------------------------------------------------- queries
    @property
    def board(self) -> Board:
        """Board of the player to move."""
        return self.boards[self.current_player]

    def overpopulated_three(self) -> Wildlife | None:
        counts = Counter(t for t in self.display_tokens if t is not None)
        for w, c in counts.items():
            if c == 3:
                return w
        return None

    def can_wipe_overpopulation(self) -> bool:
        return not self.game_over and not self.overpopulation_wipe_used and self.overpopulated_three() is not None

    def legal_pre_actions(self) -> Iterator[PreAction]:
        """All legal pre-draft actions (excluding the implicit 'proceed to draft')."""
        if self.can_wipe_overpopulation():
            yield WipeOverpopulation()
        if self.board.nature_tokens > 0:
            filled = [i for i, t in enumerate(self.display_tokens) if t is not None]
            for mask in range(1, 1 << len(filled)):
                yield NatureWipe(tuple(filled[i] for i in range(len(filled)) if mask >> i & 1))

    def draft_options(self) -> list[tuple[int, int]]:
        """(tile_slot, token_slot) choices; mixed pairs require a nature token."""
        tiles = [i for i, t in enumerate(self.display_tiles) if t is not None]
        toks = [i for i, t in enumerate(self.display_tokens) if t is not None]
        opts = [(i, i) for i in tiles if i in toks]
        if self.board.nature_tokens > 0:
            opts += [(i, j) for i in tiles for j in toks if i != j]
        return opts

    def legal_placements(self, tile_slot: int | None = None, token_slot: int | None = None) -> Iterator[Placement]:
        """Enumerate every legal placement (optionally for one draft option)."""
        board = self.board
        options = self.draft_options()
        if tile_slot is not None:
            options = [(a, b) for a, b in options if a == tile_slot and (token_slot is None or b == token_slot)]
        for ts, ks in options:
            tile = self.display_tiles[ts]
            wildlife = self.display_tokens[ks]
            assert tile is not None and wildlife is not None
            existing = board.token_spots(wildlife)
            for pos in sorted(board.frontier()):
                token_targets: list[Hex | None] = [None, *existing]
                if wildlife in tile.wildlife:
                    token_targets.append(pos)
                for rot in tile.rotations():
                    for tp in token_targets:
                        yield Placement(ts, ks, pos, rot, tp)

    # ----------------------------------------------------------------- actions
    def apply_pre_action(self, action: PreAction) -> None:
        if self.game_over:
            raise IllegalAction("game is over")
        if isinstance(action, WipeOverpopulation):
            kind = self.overpopulated_three()
            if kind is None or self.overpopulation_wipe_used:
                raise IllegalAction("no optional overpopulation wipe available")
            self.overpopulation_wipe_used = True
            self._wipe_slots([i for i, t in enumerate(self.display_tokens) if t == kind])
        elif isinstance(action, NatureWipe):
            board = self.board
            if board.nature_tokens <= 0:
                raise IllegalAction("no nature token to spend")
            slots = sorted(set(action.slots))
            if not slots or any(not 0 <= s < DISPLAY_SIZE or self.display_tokens[s] is None for s in slots):
                raise IllegalAction(f"invalid wipe slots {action.slots}")
            board.nature_tokens -= 1
            self.nature_supply += 1
            self._wipe_slots(slots)
        else:  # pragma: no cover
            raise IllegalAction(f"unknown pre-action {action!r}")
        if self.record_history:
            self.history[-1].pre_actions.append(action)
        self._resolve_four_of_a_kind()

    def check_placement(self, p: Placement) -> None:
        if self.game_over:
            raise IllegalAction("game is over")
        board = self.board
        if not (0 <= p.tile_slot < DISPLAY_SIZE and 0 <= p.token_slot < DISPLAY_SIZE):
            raise IllegalAction("slot out of range")
        tile = self.display_tiles[p.tile_slot]
        wildlife = self.display_tokens[p.token_slot]
        if tile is None or wildlife is None:
            raise IllegalAction("empty display slot")
        if p.uses_nature_token and board.nature_tokens <= 0:
            raise IllegalAction("taking a non-paired tile/token requires a nature token")
        if not board.can_place_tile(p.tile_pos):
            raise IllegalAction(f"tile cannot be placed at {p.tile_pos}")
        if not 0 <= p.rotation < 6:
            raise IllegalAction("rotation must be 0-5")
        if p.token_pos is not None:
            if p.token_pos == p.tile_pos:
                if wildlife not in tile.wildlife:
                    raise IllegalAction(f"{wildlife.name} cannot go on the new tile")
            elif not board.can_place_token(p.token_pos, wildlife):
                raise IllegalAction(f"{wildlife.name} cannot go on {p.token_pos}")

    def apply_placement(self, p: Placement) -> None:
        self.check_placement(p)
        board = self.board
        tile = self.display_tiles[p.tile_slot]
        wildlife = self.display_tokens[p.token_slot]
        assert tile is not None and wildlife is not None
        if self.record_history:
            record = self.history[-1]
            record.placement = p
            record.tile_code = tile.code
            record.wildlife = wildlife

        if p.uses_nature_token:
            board.nature_tokens -= 1
            self.nature_supply += 1
        self._return_set_aside()  # all overpopulation wipes are resolved now

        self.display_tiles[p.tile_slot] = None
        self.display_tokens[p.token_slot] = None
        board.place_tile(p.tile_pos, tile, p.rotation)
        if p.token_pos is None:
            self._bag_add([wildlife])
        else:
            if board.place_token(p.token_pos, wildlife):
                # Supply is tracked for information only; it never runs out in practice.
                self.nature_supply = max(0, self.nature_supply - 1)

        self.turns_taken[self.current_player] += 1
        self.turn += 1
        if not self._refill():
            self.game_over = True
            return
        self.current_player = (self.current_player + 1) % self.num_players
        self._begin_turn()

    def _refill(self) -> bool:
        """Refill the display. Returns False when the game ends."""
        if self.num_players == 1:
            return self._refill_solo()
        empty_tiles = [i for i, t in enumerate(self.display_tiles) if t is None]
        if len(self.tile_stack) < len(empty_tiles):
            return False
        for i in empty_tiles:
            self.display_tiles[i] = self.tile_stack.pop()
        for i, t in enumerate(self.display_tokens):
            if t is None:
                self.display_tokens[i] = self._draw_token()
        return True

    def _refill_solo(self) -> bool:
        # Draw stacks sit next to slot 0; slot 3 is the furthest from them.
        tiles = [t for t in self.display_tiles if t is not None]
        toks = [t for t in self.display_tokens if t is not None]
        if tiles:
            tiles.pop()  # discard the tile furthest from the stacks (removed from game)
        if toks:
            self.removed_tokens.append(toks.pop())  # discarded token is removed from the game
        need = DISPLAY_SIZE - len(tiles)
        if len(self.tile_stack) < need:
            self.display_tiles = [None] * (DISPLAY_SIZE - len(tiles)) + tiles
            self.display_tokens = [None] * (DISPLAY_SIZE - len(toks)) + toks
            return False
        new_tiles = [self.tile_stack.pop() for _ in range(need)]
        new_toks = [self._draw_token() for _ in range(DISPLAY_SIZE - len(toks))]
        self.display_tiles = new_tiles + tiles
        self.display_tokens = new_toks + toks
        return True

    # ----------------------------------------------------------------- scoring
    def scores(self) -> list[ScoreBreakdown]:
        """Score breakdown for every player (valid at any time; final when game over)."""
        return score_boards(self.boards, self.cards, self.habitat_majority)

    def ranking(self) -> list[int]:
        """Player indices from best to worst (ties broken by nature tokens)."""
        sc = self.scores()
        return sorted(range(self.num_players), key=lambda i: (-sc[i].total, -sc[i].nature_tokens, i))

    def winners(self) -> list[int]:
        sc = self.scores()
        key = [(s.total, s.nature_tokens) for s in sc]
        best = max(key)
        return [i for i, k in enumerate(key) if k == best]

    # ----------------------------------------------------------------- copies
    def clone(self) -> "Game":
        """Exact copy including hidden information and RNG state (for debugging/replays)."""
        g = Game.__new__(Game)
        g.__dict__.update(self.__dict__)
        g._rng = random.Random()
        g._rng.setstate(self._rng.getstate())
        g.boards = [b.copy() for b in self.boards]
        g.tile_stack = list(self.tile_stack)
        g.bag = list(self.bag)
        g.set_aside = list(self.set_aside)
        g.removed_tokens = list(self.removed_tokens)
        g.display_tiles = list(self.display_tiles)
        g.display_tokens = list(self.display_tokens)
        g.turns_taken = list(self.turns_taken)
        g.history = []  # simulations don't need the log
        g.record_history = False
        return g

    def unseen_tiles(self) -> list[Tile]:
        """Tiles not visible to anyone (in the stack or left in the box)."""
        visible = {pt.tile.id for b in self.boards for pt in b.tiles.values()}
        visible |= {t.id for t in self.display_tiles if t is not None}
        return [t for t in HABITAT_TILES if t.id not in visible]

    def determinize(self, rng: random.Random) -> "Game":
        """Copy where hidden information is resampled consistently with what is visible.

        The tile stack is redrawn from the unseen tiles (same size) and the bag
        gets a fresh RNG, so simulations cannot peek at the real future.
        """
        g = self.clone()
        g._rng = random.Random(rng.random())
        pool = self.unseen_tiles()
        g.tile_stack = rng.sample(pool, len(self.tile_stack))
        g.bag = list(self.bag)
        rng.shuffle(g.bag)
        g.sequential_bag = True
        return g
