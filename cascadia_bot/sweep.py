"""Parameter sweep: play several bot specs against one baseline on the same seeds.

For every candidate spec it plays ``--games`` 2-player games against the
baseline (seats rotated, identical seeds for every candidate) and reports the
win rate and the mean per-game score difference with its standard error.
The score difference is a much less noisy signal than the win rate.

    python -m cascadia_bot.sweep --baseline heuristic --games 200 --workers 4 \\
        mcts:depth=1 mcts:depth=2 mcts:depth=3
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time

from .arena import run_tournament


def evaluate(spec: str, baseline: str, games: int, seed: int, cards: str | None, workers: int,
             games_out: str | None = None) -> dict:
    t0 = time.time()
    _, results = run_tournament([spec, baseline], games, seed, cards, True, False, workers)
    if games_out:
        with open(games_out, "a") as f:
            for r in results:
                f.write(json.dumps({**r, "spec": spec, "baseline": baseline}) + "\n")
    diffs, wins = [], 0.0
    for r in results:
        me = r["seats"].index(spec)
        other = 1 - me
        diffs.append(r["scores"][me]["total"] - r["scores"][other]["total"])
        if me in r["winners"]:
            wins += 1.0 / len(r["winners"])
    n = len(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    return {
        "spec": spec,
        "games": n,
        "win_rate": wins / n,
        "mean_diff": statistics.fmean(diffs),
        "stderr": sd / math.sqrt(n) if n else 0.0,
        "sec_per_game": sum(r["seconds"][r["seats"].index(spec)] for r in results) / n,
        "wall": time.time() - t0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sweep bot specs against a baseline.")
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--baseline", default="heuristic")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cards", default="random")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", help="append results (one JSON object per line)")
    ap.add_argument("--games-out", help="append every individual game (one JSON object per line)")
    args = ap.parse_args(argv)
    cards = None if args.cards == "random" else args.cards

    width = max(len(s) for s in args.specs) + 2
    print(f"{'spec':<{width}}{'games':>6}{'win%':>7}{'diff':>8}{'±se':>7}{'s/game':>8}", flush=True)
    for spec in args.specs:
        res = evaluate(spec, args.baseline, args.games, args.seed, cards, args.workers, args.games_out)
        print(
            f"{spec:<{width}}{res['games']:>6}{100 * res['win_rate']:>6.1f}%{res['mean_diff']:>+8.2f}"
            f"{res['stderr']:>7.2f}{res['sec_per_game']:>8.2f}",
            flush=True,
        )
        if args.json:
            with open(args.json, "a") as f:
                f.write(json.dumps({**res, "baseline": args.baseline, "seed": args.seed}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
