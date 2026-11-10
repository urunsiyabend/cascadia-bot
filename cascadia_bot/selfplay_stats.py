"""Self-play statistics: what separates winners from losers, per-card scores, behaviour.

    python -m cascadia_bot.selfplay_stats mce --games 200 --workers 4 --out mce.jsonl
    python -m cascadia_bot.selfplay_stats --analyze mce.jsonl heuristic.jsonl

Both seats of every 2-player game are played by the same bot spec.
"""

import argparse
import json
import math
import statistics as st
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from .bots import make_bot
from .game import GameConfig, NatureWipe, WipeOverpopulation
from .runner import play_game


def run(job):
    spec, seed = job
    bots = [make_bot(spec, seed=seed * 10 + i) for i in range(2)]
    res = play_game(bots, GameConfig(num_players=2, seed=seed))
    g = res.game
    players = []
    for p in range(2):
        recs = [r for r in g.history if r.player == p and r.placement is not None]
        mixed = sum(1 for r in recs if r.placement.uses_nature_token)
        nwipes = sum(1 for r in recs for a in r.pre_actions if isinstance(a, NatureWipe))
        owipes = sum(1 for r in recs for a in r.pre_actions if isinstance(a, WipeOverpopulation))
        discarded = sum(1 for r in recs if r.placement.token_pos is None)
        board = g.boards[p]
        keystone_tokens = sum(1 for pos in board.tokens if board.tiles[pos].tile.keystone)
        sc = res.scores[p]
        players.append(
            {
                "total": sc.total,
                "wildlife": {w.name.lower(): v for w, v in sc.wildlife.items()},
                "habitat": sum(sc.habitat.values()),
                "bonus": sum(sc.habitat_bonus.values()),
                "nature_left": sc.nature_tokens,
                "nature_earned": keystone_tokens,
                "mixed_drafts": mixed,
                "nature_wipes": nwipes,
                "overpop_wipes": owipes,
                "tokens_placed": len(board.tokens),
                "discarded": discarded,
            }
        )
    return {"seed": seed, "cards": str(g.cards), "winners": res.winners, "players": players}


ANIMALS = ["bear", "elk", "salmon", "hawk", "fox"]


def load(path):
    return [json.loads(line) for line in open(path)]


def cats(p):
    d = {a: p["wildlife"][a] for a in ANIMALS}
    d["wildlife"] = sum(p["wildlife"].values())
    d["habitat"] = p["habitat"]
    d["bonus"] = p["bonus"]
    d["nature_left"] = p["nature_left"]
    d["total"] = p["total"]
    return d


def mse(xs):
    return st.fmean(xs), (st.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0)


def report(path):
    games = load(path)
    print(f"\n### {path}  ({len(games)} games)")
    # averages
    allp = [cats(p) for g in games for p in g["players"]]
    keys = list(allp[0])
    print("averages per player: " + ", ".join(f"{k}={st.fmean(d[k] for d in allp):.1f}" for k in keys))
    beh = defaultdict(list)
    for g in games:
        for p in g["players"]:
            for k in ("nature_earned", "mixed_drafts", "nature_wipes", "overpop_wipes", "tokens_placed", "discarded"):
                beh[k].append(p[k])
    print("behaviour per player: " + ", ".join(f"{k}={st.fmean(v):.2f}" for k, v in beh.items()))
    # winner - loser
    diffs = defaultdict(list)
    wins_more = defaultdict(int)
    n = 0
    for g in games:
        if len(g["winners"]) != 1:
            continue
        w = g["winners"][0]
        a, b = cats(g["players"][w]), cats(g["players"][1 - w])
        n += 1
        for k in keys:
            diffs[k].append(a[k] - b[k])
            wins_more[k] += a[k] > b[k]
    print(f"winner minus loser ({n} decisive games): mean ± se, share of games winner had more")
    for k in keys:
        m, se = mse(diffs[k])
        print(f"  {k:12s} {m:+6.2f} ± {se:4.2f}   {100 * wins_more[k] / n:5.1f}%")
    # per card average score
    per = defaultdict(list)
    for g in games:
        cards = g["cards"]
        if len(cards) != 5:
            continue
        for p in g["players"]:
            for i, a in enumerate(ANIMALS):
                per[(a, cards[i])].append(p["wildlife"][a])
    print("average wildlife score per card:")
    for a in ANIMALS:
        print("  " + a.ljust(7) + "  ".join(f"{c}={st.fmean(per[(a, c)]):5.1f}" for c in "ABCD" if per[(a, c)]))
    return games


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", nargs="?", help="bot spec for both seats")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--seed", type=int, default=80000)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", help="jsonl file for the raw game records")
    ap.add_argument("--analyze", nargs="+", help="only analyse existing jsonl files")
    args = ap.parse_args(argv)
    if args.analyze:
        for path in args.analyze:
            report(path)
        return 0
    if not args.spec:
        ap.error("give a bot spec or --analyze files")
    out = args.out or f"selfplay_{args.spec.replace(':', '_').replace(',', '_')}.jsonl"
    jobs = [(args.spec, args.seed + k) for k in range(args.games)]
    with open(out, "w") as f:
        if args.workers > 1:
            with ProcessPoolExecutor(args.workers) as ex:
                for r in ex.map(run, jobs):
                    f.write(json.dumps(r) + "\n")
        else:
            for job in jobs:
                f.write(json.dumps(run(job)) + "\n")
    report(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
