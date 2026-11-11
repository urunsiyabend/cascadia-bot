"""Randomness and reproducibility checks for the replanning study (preregistration section 4.3).

1. Isolation: no agent decision touches the game's draw RNG or hidden state.
2. Determinism: the same seed and configuration give the identical game, also in a
   fresh process with a different PYTHONHASHSEED and with a different worker count.
3. Shared randomness: what a seed fixes across *different* agents (cards, starters,
   initial display, tile order, token order) under token_order=random vs presorted.

    python experiments/replanning/check_rng.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cascadia_bot.bots import make_bot  # noqa: E402
from cascadia_bot.game import Game, GameConfig  # noqa: E402

CHECK_SEEDS = range(3_100_000, 3_100_000 + 3)  # development range, outside the confirmatory seeds
ISOLATION_SPECS = [
    "greedy",
    "heuristic",
    "value",
    "greedy:nature_wipes=true",
    "lookahead:top_k=2,samples=1",
    "mcts:iterations=8,top_k=3",
    "mce:playouts=6,top_k=3",
    "plan:replan=always,samples=1,check_every=4",
    "plan:replan=never,samples=2",
]


def fingerprint(g: Game) -> tuple:
    return (
        g._rng.getstate(),
        tuple(g.bag),
        tuple(t.id for t in g.tile_stack),
        tuple(t.id if t else None for t in g.display_tiles),
        tuple(g.display_tokens),
        tuple(tuple(sorted(b.tokens.items())) for b in g.boards),
        tuple(tuple(sorted((p, pt.tile.id, pt.rotation) for p, pt in b.tiles.items())) for b in g.boards),
        tuple(b.nature_tokens for b in g.boards),
    )


def check_isolation() -> None:
    for token_order in ("random", "presorted"):
        for spec in ISOLATION_SPECS:
            seed = CHECK_SEEDS[0]
            bots = [make_bot(spec, seed=1), make_bot("greedy", seed=2)]
            g = Game(GameConfig(num_players=2, seed=seed, token_order=token_order))
            for i, b in enumerate(bots):
                b.reset(g, i)
            while not g.game_over:
                bot = bots[g.current_player]
                for _ in range(8):
                    before = fingerprint(g)
                    action = bot.choose_pre_action(g)
                    assert fingerprint(g) == before, f"{spec}: choose_pre_action changed the game"
                    if action is None:
                        break
                    g.apply_pre_action(action)
                before = fingerprint(g)
                placement = bot.choose_placement(g)
                assert fingerprint(g) == before, f"{spec}: choose_placement changed the game"
                g.apply_placement(placement)
    print(f"[ok] isolation: {len(ISOLATION_SPECS)} agents x 2 token orders never changed RNG state or game state")


def play(spec: str, seed: int, token_order: str) -> dict:
    bots = [make_bot(spec, seed=10 * seed), make_bot("greedy", seed=10 * seed + 1)]
    from cascadia_bot.runner import play_game

    res = play_game(bots, GameConfig(num_players=2, seed=seed, token_order=token_order))
    hist = [(r.player, r.tile_code, int(r.wildlife) if r.wildlife is not None else None,
             None if r.placement is None else (r.placement.tile_pos, r.placement.rotation, r.placement.token_pos))
            for r in res.game.history]
    return {"scores": res.totals, "history": hist}


def check_determinism() -> None:
    for token_order in ("random", "presorted"):
        for spec in ("plan:replan=always,samples=2,check_every=3", "mce:playouts=8,top_k=3"):
            for seed in CHECK_SEEDS[:2]:
                a, b = play(spec, seed, token_order), play(spec, seed, token_order)
                assert a == b, f"{spec} seed {seed} not reproducible in-process"
    print("[ok] determinism in-process: identical history and scores on repeated runs")

    with tempfile.TemporaryDirectory() as tmp:
        outs = []
        for hashseed, workers in (("0", "1"), ("12345", "2")):
            out = Path(tmp) / f"g_{hashseed}_{workers}.jsonl"
            env = dict(os.environ, PYTHONHASHSEED=hashseed)
            subprocess.run(
                [sys.executable, "-m", "cascadia_bot.sweep", "plan:replan=always,samples=2,check_every=3",
                 "--baseline", "greedy", "--games", "4", "--seed", str(CHECK_SEEDS[0]), "--workers", workers,
                 "--token-order", "presorted", "--games-out", str(out)],
                cwd=ROOT, env=env, check=True, capture_output=True,
            )
            rows = []
            for line in out.read_text().splitlines():
                r = json.loads(line)
                r.pop("seconds", None)
                rows.append(r)
            outs.append(sorted(rows, key=lambda r: (r["seed"], r["seats"])))
        assert outs[0] == outs[1], "results differ across processes / PYTHONHASHSEED / worker counts"
    print("[ok] determinism across processes: PYTHONHASHSEED 0 vs 12345 and 1 vs 2 workers give identical games")


def draw_log(spec: str, seed: int, token_order: str) -> dict:
    """Play one game and record everything the seed is supposed to fix."""
    tokens_drawn: list[int] = []
    original = Game._draw_token

    def logged(self):
        t = original(self)
        if t is not None:
            tokens_drawn.append(int(t))
        return t

    Game._draw_token = logged
    try:
        bots = [make_bot(spec, seed=10 * seed), make_bot("greedy", seed=10 * seed + 1)]
        g = Game(GameConfig(num_players=2, seed=seed, token_order=token_order))
        info = {
            "cards": str(g.cards),
            "starters": tuple(g.starter_indices),
            "display": (tuple(t.id for t in g.display_tiles), tuple(int(t) for t in g.display_tokens)),
        }
        tiles_seen = [t.id for t in g.display_tiles]
        while not g.game_over:
            before = {t.id for t in g.display_tiles if t}
            g.apply_placement(bots[g.current_player].choose_placement(g))
            tiles_seen += [t.id for t in g.display_tiles if t and t.id not in before]
        info["tiles"] = tiles_seen
        info["tokens"] = tokens_drawn
        return info
    finally:
        Game._draw_token = original


def check_shared_randomness(n: int = 30) -> None:
    print("[info] what one seed fixes across different agents (heuristic vs value, both against greedy):")
    for token_order in ("random", "presorted"):
        same = {"cards": 0, "starters": 0, "display": 0}
        tile_prefix, token_match, token_prefix = [], [], []
        for seed in range(3_200_000, 3_200_000 + n):
            a = draw_log("heuristic", seed, token_order)
            b = draw_log("value", seed, token_order)
            for k in same:
                same[k] += a[k] == b[k]
            m = min(len(a["tiles"]), len(b["tiles"]))
            tile_prefix.append(sum(1 for i in range(m) if a["tiles"][i] == b["tiles"][i]) / m)
            m = min(len(a["tokens"]), len(b["tokens"]))
            token_match.append(sum(1 for i in range(m) if a["tokens"][i] == b["tokens"][i]) / m)
            p = 0
            while p < m and a["tokens"][p] == b["tokens"][p]:
                p += 1
            token_prefix.append(p)
        print(f"  token_order={token_order:9s} identical cards {same['cards']}/{n}, starters {same['starters']}/{n}, "
              f"initial display {same['display']}/{n}; tiles in identical order {100 * sum(tile_prefix) / n:.0f}%; "
              f"drawn tokens equal position-by-position {100 * sum(token_match) / n:.0f}% "
              f"(chance 20%); identical token prefix {sum(token_prefix) / n:.1f} draws on average")


if __name__ == "__main__":
    check_isolation()
    check_determinism()
    check_shared_randomness()
