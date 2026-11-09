"""Game components: habitats, wildlife, habitat tiles and starter tiles.

Component counts follow the base game:

* 85 habitat tiles: 25 keystone tiles (single habitat, single wildlife; 5 per
  habitat) and 60 dual-habitat tiles (6 for each of the 10 habitat pairs) showing
  2 or 3 wildlife options.
* 5 starter habitat tiles, each made of 3 hexes (1 keystone + 2 dual hexes).
* 100 wildlife tokens (20 of each wildlife), 25 nature tokens.

Tile notation used in the definitions below: two habitat letters followed by the
wildlife letters that may be placed on the tile.

    Habitats: M=mountain F=forest P=prairie W=wetland R=river
    Wildlife: b=bear e=elk s=salmon h=hawk f=fox

``"FFb"`` is a forest keystone tile that accepts a bear, ``"FPsef"`` is a
forest/prairie tile accepting salmon, elk or fox.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from functools import cached_property

from .hexgrid import Hex


class Habitat(IntEnum):
    MOUNTAIN = 0
    FOREST = 1
    PRAIRIE = 2
    WETLAND = 3
    RIVER = 4

    @property
    def letter(self) -> str:
        return HABITAT_LETTERS[self]


class Wildlife(IntEnum):
    BEAR = 0
    ELK = 1
    SALMON = 2
    HAWK = 3
    FOX = 4

    @property
    def letter(self) -> str:
        return WILDLIFE_LETTERS[self]


HABITAT_LETTERS = {
    Habitat.MOUNTAIN: "M",
    Habitat.FOREST: "F",
    Habitat.PRAIRIE: "P",
    Habitat.WETLAND: "W",
    Habitat.RIVER: "R",
}
WILDLIFE_LETTERS = {
    Wildlife.BEAR: "b",
    Wildlife.ELK: "e",
    Wildlife.SALMON: "s",
    Wildlife.HAWK: "h",
    Wildlife.FOX: "f",
}
HABITAT_BY_LETTER = {v: k for k, v in HABITAT_LETTERS.items()}
WILDLIFE_BY_LETTER = {v: k for k, v in WILDLIFE_LETTERS.items()}

TOKENS_PER_WILDLIFE = 20
NATURE_TOKEN_SUPPLY = 25
DISPLAY_SIZE = 4
TURNS_PER_PLAYER = 20


@dataclass(frozen=True)
class Tile:
    """A single habitat hex (keystone or dual-habitat)."""

    id: int
    habitats: tuple[Habitat, ...]  # length 1 (keystone) or 2
    wildlife: frozenset[Wildlife]
    code: str = field(compare=False)

    @property
    def keystone(self) -> bool:
        return len(self.habitats) == 1

    def rotations(self) -> tuple[int, ...]:
        """Distinct rotations: a keystone tile looks the same in every rotation."""
        return (0,) if self.keystone else (0, 1, 2, 3, 4, 5)

    @cached_property
    def _edges(self) -> tuple[tuple[Habitat, ...], ...]:
        if self.keystone:
            h = self.habitats[0]
            return tuple((h,) * 6 for _ in range(6))
        h1, h2 = self.habitats
        out = []
        for rot in range(6):
            first = {(rot + i) % 6 for i in range(3)}
            out.append(tuple(h1 if d in first else h2 for d in range(6)))
        return tuple(out)

    @cached_property
    def _edge_masks(self) -> tuple[tuple[tuple[Habitat, int], ...], ...]:
        out = []
        for rot in range(6):
            e = self._edges[rot]
            out.append(tuple((h, sum(1 << d for d in range(6) if e[d] == h)) for h in self.habitats))
        return tuple(out)

    def edge_masks(self, rotation: int) -> tuple[tuple[Habitat, int], ...]:
        """For each habitat of the tile: bitmask of the edge directions showing it."""
        return self._edge_masks[rotation % 6]

    def edges(self, rotation: int) -> tuple[Habitat, ...]:
        """Habitat on each of the six edges for the given rotation.

        For a dual tile, the first habitat occupies edges ``rotation``,
        ``rotation+1`` and ``rotation+2`` (mod 6); the second habitat the rest.
        """
        return self._edges[rotation % 6]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Tile#{self.id}({self.code})"


def parse_tile(tile_id: int, code: str) -> Tile:
    h1, h2, *ws = code
    habitats = (HABITAT_BY_LETTER[h1],) if h1 == h2 else (HABITAT_BY_LETTER[h1], HABITAT_BY_LETTER[h2])
    wildlife = frozenset(WILDLIFE_BY_LETTER[w] for w in ws)
    if not wildlife:
        raise ValueError(f"tile {code!r} has no wildlife")
    return Tile(tile_id, habitats, wildlife, code)


# fmt: off
HABITAT_TILE_CODES: tuple[str, ...] = (
    # Keystone tiles (25)
    "MMb", "MMe", "MMe", "MMh", "MMh",
    "FFb", "FFb", "FFe", "FFf", "FFf",
    "PPe", "PPe", "PPf", "PPs", "PPs",
    "WWf", "WWf", "WWh", "WWs", "WWs",
    "RRb", "RRb", "RRh", "RRh", "RRs",
    # Dual-habitat tiles (60)
    "FPbe", "FPbf", "FPef", "FPes", "FPfs", "FPsef",
    "FRbs", "FReb", "FReh", "FRfb", "FRfs", "FRhef",
    "FWbf", "FWbs", "FWeh", "FWes", "FWfh", "FWseh",
    "MFbf", "MFef", "MFfeb", "MFhb", "MFhe", "MFheb",
    "MPbs", "MPes", "MPfeb", "MPhe", "MPhf", "MPsbf",
    "MWbs", "MWef", "MWeh", "MWfbh", "MWhs", "MWseb",
    "PReh", "PRes", "PRfb", "PRfbh", "PRfh", "PRsbf",
    "PWef", "PWes", "PWfh", "PWsef", "PWsh", "PWshf",
    "RMbe", "RMhb", "RMhe", "RMsb", "RMsbh", "RMsh",
    "WRfh", "WRfs", "WRhb", "WRsb", "WRsbh", "WRsh",
)

#: Starter habitat tiles: three hexes each, given as (position, tile code, rotation).
#: The first hex is the keystone part of the starter tile.
STARTER_TILE_LAYOUTS: tuple[tuple[tuple[Hex, str, int], ...], ...] = (
    (((0, 1), "MMb", 0), ((0, 0), "FWhef", 4), ((1, 0), "RPsb", 5)),
    (((0, 1), "RRs", 0), ((0, 0), "PFseb", 4), ((1, 0), "MWfh", 5)),
    (((0, 1), "PPf", 0), ((0, 0), "WRshf", 4), ((1, 0), "FMbe", 5)),
    (((0, 1), "FFe", 0), ((0, 0), "MRheb", 4), ((1, 0), "WPfs", 5)),
    (((0, 1), "WWh", 0), ((0, 0), "RFseh", 4), ((1, 0), "PMbf", 5)),
)
# fmt: on

HABITAT_TILES: tuple[Tile, ...] = tuple(parse_tile(i, code) for i, code in enumerate(HABITAT_TILE_CODES))
TILE_BY_ID: dict[int, Tile] = {t.id: t for t in HABITAT_TILES}

_STARTER_ID_BASE = 1000
STARTER_TILES: tuple[tuple[tuple[Hex, Tile, int], ...], ...] = tuple(
    tuple(
        (pos, parse_tile(_STARTER_ID_BASE + 10 * s + i, code), rot)
        for i, (pos, code, rot) in enumerate(layout)
    )
    for s, layout in enumerate(STARTER_TILE_LAYOUTS)
)


def tiles_for_player_count(num_players: int) -> int:
    """Number of habitat tiles used: 20 per player + 3 (solo uses the 2-player count)."""
    if num_players == 1:
        return 43
    if 2 <= num_players <= 4:
        return 20 * num_players + 3
    raise ValueError("Cascadia supports 1-4 players")
