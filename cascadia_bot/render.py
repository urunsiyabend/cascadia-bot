"""Plain-text rendering of boards and the display (debugging aid)."""

from __future__ import annotations

from .board import Board
from .game import Game

CELL = 8  # characters per hex


def _cell_text(board: Board, pos) -> str:
    placed = board.tiles[pos]
    tile = placed.tile
    hab = "".join(h.letter for h in tile.habitats)
    token = board.tokens.get(pos)
    if token is not None:
        wild = token.letter.upper()
    else:
        wild = "".join(sorted(w.letter for w in tile.wildlife))
    star = "*" if tile.keystone else ""
    return f"{hab}{star}:{wild}"


def render_board(board: Board) -> str:
    """Rows of hexes (pointy-top layout). ``F*:B`` = forest keystone with a bear,
    ``MW:beh`` = empty mountain/wetland tile accepting bear, elk or hawk."""
    if not board.tiles:
        return "(empty)"
    rs = [p[1] for p in board.tiles]
    xs = {p: 2 * p[0] + p[1] for p in board.tiles}  # doubled x coordinate
    min_x = min(xs.values())
    lines = []
    for r in range(min(rs), max(rs) + 1):
        row = [p for p in board.tiles if p[1] == r]
        if not row:
            lines.append("")
            continue
        width = (max(xs[p] for p in row) - min_x) // 1 * (CELL // 2) + CELL
        buf = [" "] * width
        for p in row:
            start = (xs[p] - min_x) * (CELL // 2)
            text = _cell_text(board, p)[: CELL - 1].ljust(CELL - 1)
            buf[start : start + len(text)] = list(text)
        lines.append("".join(buf).rstrip())
    return "\n".join(lines)


def render_display(game: Game) -> str:
    parts = []
    for i, (t, w) in enumerate(zip(game.display_tiles, game.display_tokens)):
        tile = "--" if t is None else t.code
        tok = "-" if w is None else w.name.lower()
        parts.append(f"[{i}] {tile} + {tok}")
    return "   ".join(parts)


def render_game(game: Game) -> str:
    out = [f"Turn {game.turn}  player to move: {game.current_player}  cards: {game.cards}"]
    out.append("Display: " + render_display(game))
    for i, b in enumerate(game.boards):
        out.append(f"\n-- Player {i} (nature tokens: {b.nature_tokens}) --")
        out.append(render_board(b))
    return "\n".join(out)
