"""A player's environment: placed habitat tiles, wildlife tokens and nature tokens."""

from __future__ import annotations

from .components import STARTER_TILES, Habitat, Tile, Wildlife
from .hexgrid import DIRECTIONS, Hex, neighbors, opposite


class PlacedTile:
    __slots__ = ("tile", "rotation", "edges")

    def __init__(self, tile: Tile, rotation: int):
        self.tile = tile
        self.rotation = rotation % 6 if not tile.keystone else 0
        self.edges = tile.edges(self.rotation)

    def __repr__(self) -> str:  # pragma: no cover
        return f"PlacedTile({self.tile.code}, rot={self.rotation})"


class Board:
    """Tiles and tokens of one player.

    ``tiles`` maps hex -> PlacedTile, ``tokens`` maps hex -> Wildlife.
    """

    def __init__(self) -> None:
        self.tiles: dict[Hex, PlacedTile] = {}
        self.tokens: dict[Hex, Wildlife] = {}
        self.nature_tokens: int = 0
        self._frontier: set[Hex] = set()
        self._corridor_cache: dict[Habitat, tuple[dict[Hex, int], list[int]]] | None = None
        self._probe: CorridorProbe | None = None

    # ------------------------------------------------------------------ setup
    @classmethod
    def with_starter(cls, starter_index: int) -> "Board":
        board = cls()
        for pos, tile, rot in STARTER_TILES[starter_index]:
            board._put_tile(pos, tile, rot)
        return board

    def copy(self) -> "Board":
        b = Board.__new__(Board)
        b.tiles = dict(self.tiles)  # PlacedTile objects are immutable in practice
        b.tokens = dict(self.tokens)
        b.nature_tokens = self.nature_tokens
        b._frontier = set(self._frontier)
        b._corridor_cache = self._corridor_cache
        b._probe = self._probe
        return b

    # ------------------------------------------------------------- tiles
    def _put_tile(self, pos: Hex, tile: Tile, rotation: int) -> None:
        self.tiles[pos] = PlacedTile(tile, rotation)
        self._frontier.discard(pos)
        for n in neighbors(pos):
            if n not in self.tiles:
                self._frontier.add(n)
        self._corridor_cache = None
        self._probe = None

    def frontier(self) -> set[Hex]:
        """Empty hexes adjacent to at least one tile (legal tile positions)."""
        return self._frontier

    def can_place_tile(self, pos: Hex) -> bool:
        return pos in self._frontier

    def place_tile(self, pos: Hex, tile: Tile, rotation: int) -> None:
        if not self.can_place_tile(pos):
            raise ValueError(f"illegal tile position {pos}")
        self._put_tile(pos, tile, rotation)

    # ------------------------------------------------------------- tokens
    def can_place_token(self, pos: Hex, wildlife: Wildlife) -> bool:
        placed = self.tiles.get(pos)
        return placed is not None and pos not in self.tokens and wildlife in placed.tile.wildlife

    def token_spots(self, wildlife: Wildlife) -> list[Hex]:
        """Tiles that can currently receive a token of this wildlife."""
        return [
            pos
            for pos, placed in self.tiles.items()
            if wildlife in placed.tile.wildlife and pos not in self.tokens
        ]

    def place_token(self, pos: Hex, wildlife: Wildlife) -> bool:
        """Place a token. Returns True when a nature token was earned (keystone)."""
        if not self.can_place_token(pos, wildlife):
            raise ValueError(f"illegal {wildlife.name} token position {pos}")
        self.tokens[pos] = wildlife
        if self.tiles[pos].tile.keystone:
            self.nature_tokens += 1
            return True
        return False

    def wildlife_positions(self, wildlife: Wildlife) -> set[Hex]:
        return {p for p, w in self.tokens.items() if w == wildlife}

    # ------------------------------------------------------------- corridors
    def _corridors(self) -> dict[Habitat, tuple[dict[Hex, int], list[int]]]:
        """Per habitat: (hex -> component id, component sizes)."""
        if self._corridor_cache is not None:
            return self._corridor_cache
        result: dict[Habitat, tuple[dict[Hex, int], list[int]]] = {}
        for habitat in Habitat:
            comp: dict[Hex, int] = {}
            sizes: list[int] = []
            for start, placed in self.tiles.items():
                if start in comp or habitat not in placed.tile.habitats:
                    continue
                cid = len(sizes)
                comp[start] = cid
                size = 1
                stack = [start]
                while stack:
                    cur = stack.pop()
                    cur_edges = self.tiles[cur].edges
                    for d, (dq, dr) in enumerate(DIRECTIONS):
                        if cur_edges[d] != habitat:
                            continue
                        n = (cur[0] + dq, cur[1] + dr)
                        if n in comp:
                            continue
                        other = self.tiles.get(n)
                        if other is None or other.edges[opposite(d)] != habitat:
                            continue
                        comp[n] = cid
                        size += 1
                        stack.append(n)
                sizes.append(size)
            result[habitat] = (comp, sizes)
        self._corridor_cache = result
        return result

    def largest_corridor(self, habitat: Habitat) -> int:
        sizes = self._corridors()[habitat][1]
        return max(sizes, default=0)

    def largest_corridors(self) -> dict[Habitat, int]:
        return {h: self.largest_corridor(h) for h in Habitat}

    def probe(self) -> "CorridorProbe":
        """Fast what-if corridor queries for the current tiles (cached until a tile is placed)."""
        if self._probe is None:
            self._probe = CorridorProbe(self)
        return self._probe

    def corridor_sizes_after(self, pos: Hex, tile: Tile, rotation: int) -> dict[Habitat, int]:
        """Largest corridor size for each habitat of ``tile`` if it were placed at ``pos``.

        Computed incrementally without mutating the board.
        """
        corridors = self._corridors()
        edges = tile.edges(rotation)
        out: dict[Habitat, int] = {}
        for habitat in tile.habitats:
            comp, sizes = corridors[habitat]
            joined: set[int] = set()
            for d, n in enumerate(neighbors(pos)):
                if edges[d] != habitat:
                    continue
                other = self.tiles.get(n)
                if other is None or other.edges[opposite(d)] != habitat:
                    continue
                joined.add(comp[n])
            new_size = 1 + sum(sizes[c] for c in joined)
            out[habitat] = max(new_size, max(sizes, default=0))
        return out

    # ------------------------------------------------------------- misc
    def __len__(self) -> int:
        return len(self.tiles)


class CorridorProbe:
    """Answers "largest corridor per habitat if ``tile`` were placed at ``pos``" quickly.

    For every candidate hex it records, per habitat, which neighbour directions
    face that habitat and which corridor component they belong to. A query is
    then a few bit operations; results are memoised per (hex, habitat, edge mask).
    """

    __slots__ = ("largest", "_sizes", "_comp", "_tiles", "_face", "_memo", "_arcs")

    def __init__(self, board: Board):
        corridors = board._corridors()
        self.largest = {h: max(sizes, default=0) for h, (_, sizes) in corridors.items()}
        self._sizes = {h: sizes for h, (_, sizes) in corridors.items()}
        self._comp = {h: comp for h, (comp, _) in corridors.items()}
        self._tiles = board.tiles
        self._face: dict[Hex, list[list[tuple[int, int]]]] = {}
        self._memo: dict[tuple[Hex, Habitat, int], int] = {}
        self._arcs: dict[Hex, list[tuple[int, ...]]] = {}

    def _facing(self, pos: Hex) -> list[list[tuple[int, int]]]:
        face = self._face.get(pos)
        if face is None:
            face = [[] for _ in _HABITATS]
            tiles = self._tiles
            for d, n in enumerate(neighbors(pos)):
                other = tiles.get(n)
                if other is None:
                    continue
                h = other.edges[(d + 3) % 6]
                face[h].append((1 << d, self._comp[h][n]))
            self._face[pos] = face
        return face

    def new_corridor_size(self, pos: Hex, habitat: Habitat, edge_mask: int) -> int:
        """Size of the corridor the new tile's ``habitat`` part would belong to."""
        key = (pos, habitat, edge_mask)
        size = self._memo.get(key)
        if size is None:
            comps = {c for bit, c in self._facing(pos)[habitat] if bit & edge_mask}
            sizes = self._sizes[habitat]
            size = 1 + sum(sizes[c] for c in comps)
            self._memo[key] = size
        return size

    def sizes_after(self, pos: Hex, tile: Tile, rotation: int) -> dict[Habitat, int]:
        out = {}
        for habitat, mask in tile.edge_masks(rotation):
            new = self.new_corridor_size(pos, habitat, mask)
            largest = self.largest[habitat]
            out[habitat] = new if new > largest else largest
        return out

    def arc_sizes(self, pos: Hex) -> list[tuple[int, ...]]:
        """Per habitat: new corridor sizes for the 6 half-tile arcs and the full tile.

        Index ``r`` (0-5) is the arc on edges ``r, r+1, r+2`` - the first habitat
        of a dual tile at rotation ``r`` (its second habitat uses arc ``r+3``);
        index 6 is a keystone tile (all six edges).
        """
        arcs = self._arcs.get(pos)
        if arcs is None:
            face = self._facing(pos)
            arcs = []
            for h in _HABITATS:
                entries = face[h]
                if not entries:
                    arcs.append(_NO_JOIN)
                    continue
                sizes = self._sizes[h]
                if len(entries) == 1:
                    bit, c = entries[0]
                    joined = 1 + sizes[c]
                    arcs.append(tuple(joined if bit & m else 1 for m in _ARC_MASKS))
                    continue
                row = []
                for mask in _ARC_MASKS:
                    comps = {c for bit, c in entries if bit & mask}
                    row.append(1 + sum(sizes[c] for c in comps))
                arcs.append(tuple(row))
            self._arcs[pos] = arcs
        return arcs


_ARC_MASKS = tuple(sum(1 << ((r + i) % 6) for i in range(3)) for r in range(6)) + (63,)
_NO_JOIN = (1,) * 7
_HABITATS = tuple(Habitat)
