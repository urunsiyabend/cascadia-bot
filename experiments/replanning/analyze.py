"""Pre-specified analysis for the replanning confirmatory study (docs/preregistration.md).

Input: per-game records written by ``python -m cascadia_bot.sweep --games-out``.
Every condition plays the same seeds and seat orders against ``greedy``, so
games are paired across conditions by (seed, seat of the agent).

    python experiments/replanning/analyze.py results/replanning/primary_games.jsonl [--secondary]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
from collections import defaultdict

# Condition labels -> bot specs (must match docs/preregistration.md)
PRIMARY = {
    "NEVER": "plan:replan=never,samples=62",
    "EV-1": "plan:replan=ev,check_every=1,samples=6",
    "EV-3": "plan:replan=ev,check_every=3,samples=16",
    "ALWAYS-1": "plan:replan=always,check_every=1,samples=6",
    "ALWAYS-3": "plan:replan=always,check_every=3,samples=16",
}
PRIMARY_CONTRASTS = [  # (name, A, B): estimate of A - B
    ("C1 frequency (always)", "ALWAYS-1", "ALWAYS-3"),
    ("C2 frequency (ev)", "EV-1", "EV-3"),
    ("C3 flexibility vs commitment", "ALWAYS-1", "NEVER"),
    ("C4 rule (every turn)", "ALWAYS-1", "EV-1"),
    ("C5 rule (every 3 turns)", "ALWAYS-3", "EV-3"),
]
SECONDARY = {
    "EV-1x3": "plan:replan=ev,check_every=1,samples=18",
    "ALWAYS-1x3": "plan:replan=always,check_every=1,samples=18",
}
SECONDARY_CONTRASTS = [
    ("S1 budget x3 (ev, every turn)", "EV-1x3", "EV-1"),
    ("S2 budget x3 (always, every turn)", "ALWAYS-1x3", "ALWAYS-1"),
]
ALPHA = 0.05
SESOI = 0.5  # smallest effect size of interest, points per game
BOOTSTRAP = 10000


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def load(path: str, conditions: dict[str, str]) -> dict[str, dict[tuple[int, int], dict]]:
    by_spec = {spec: label for label, spec in conditions.items()}
    games: dict[str, dict[tuple[int, int], dict]] = defaultdict(dict)
    for line in open(path):
        r = json.loads(line)
        label = by_spec.get(r["spec"])
        if label is None:
            continue
        seat = r["seats"].index(r["spec"])
        key = (r["seed"], seat)
        if key in games[label]:
            raise SystemExit(f"duplicate game {key} for {label}: games must be unique")
        totals = [s["total"] for s in r["scores"]]
        stats = r.get("bot_stats", [{}, {}])[seat]
        games[label][key] = {
            "diff": totals[seat] - totals[1 - seat],
            "win": (1.0 / len(r["winners"])) if seat in r["winners"] else 0.0,
            "switches": stats.get("switches"),
            "sim": stats.get("sim_decisions"),
            "sec": r["seconds"][seat],
        }
    return games


def describe(label: str, g: dict) -> str:
    d = [x["diff"] for x in g.values()]
    n = len(d)
    se = st.stdev(d) / math.sqrt(n)
    win = st.fmean(x["win"] for x in g.values())
    sw = [x["switches"] for x in g.values() if x["switches"] is not None]
    sim = [x["sim"] for x in g.values() if x["sim"] is not None]
    return (f"| {label} | {n} | {st.fmean(d):+.2f} ± {se:.2f} | {100 * win:.1f}% | "
            f"{st.fmean(sw) if sw else float('nan'):.2f} | {st.fmean(sim) if sim else float('nan'):.0f} | "
            f"{st.fmean(x['sec'] for x in g.values()):.1f} |")


def contrast(a: dict, b: dict, rng: random.Random, subset_ok: bool = False) -> dict:
    """Paired contrast A - B over games with the same (seed, seat).

    Primary conditions must cover identical game sets. Secondary (budget x3)
    conditions are played on a pre-specified subset of the primary seeds.
    """
    keys = sorted(set(a) & set(b))
    if subset_ok:
        if len(keys) != min(len(a), len(b)):
            raise SystemExit("secondary games are not a subset of the primary games")
    elif len(keys) != len(a) or len(keys) != len(b):
        raise SystemExit("conditions are not played on identical (seed, seat) sets")
    d = [a[k]["diff"] - b[k]["diff"] for k in keys]
    n = len(d)
    mean = st.fmean(d)
    se = st.stdev(d) / math.sqrt(n)
    z = mean / se if se > 0 else 0.0
    p = 2 * norm_sf(abs(z))
    boots = sorted(st.fmean(rng.choices(d, k=n)) for _ in range(BOOTSTRAP))
    ci95 = (boots[int(0.025 * BOOTSTRAP)], boots[int(0.975 * BOOTSTRAP) - 1])
    ci90 = (mean - 1.6449 * se, mean + 1.6449 * se)
    corr = st.correlation([a[k]["diff"] for k in keys], [b[k]["diff"] for k in keys])
    return {"n": n, "mean": mean, "se": se, "z": z, "p": p, "ci95": ci95, "ci90": ci90, "corr": corr}


def holm(ps: list[float], alpha: float) -> list[bool]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    reject = [False] * len(ps)
    for rank, i in enumerate(order):
        if ps[i] <= alpha / (len(ps) - rank):
            reject[i] = True
        else:
            break
    return reject


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("games")
    ap.add_argument("--secondary", action="store_true", help="analyse the budget-sensitivity conditions")
    args = ap.parse_args()
    conditions = dict(PRIMARY)
    contrasts = PRIMARY_CONTRASTS
    if args.secondary:
        conditions.update(SECONDARY)
        contrasts = SECONDARY_CONTRASTS
    games = load(args.games, conditions)
    rng = random.Random(12345)

    print("| Condition | Games | Score diff vs greedy (± SE) | Win share | Switches/game | Sim. decisions/game | s/game |")
    print("|---|---|---|---|---|---|---|")
    for label in conditions:
        if label in games:
            print(describe(label, games[label]))

    results = [(name, contrast(games[a], games[b], rng, subset_ok=args.secondary)) for name, a, b in contrasts]
    rejects = holm([r["p"] for _, r in results], ALPHA)
    family = "primary (Holm, family alpha 0.05)" if not args.secondary else "secondary (Holm within family)"
    print(f"\nContrasts, {family}; SESOI ±{SESOI} points")
    print("| Contrast | n | Estimate (A−B) | 95% bootstrap CI | p | Holm | Equivalent (90% CI within ±SESOI) | r |")
    print("|---|---|---|---|---|---|---|---|")
    for (name, r), rej in zip(results, rejects):
        equiv = r["ci90"][0] > -SESOI and r["ci90"][1] < SESOI
        print(f"| {name} | {r['n']} | {r['mean']:+.2f} ± {r['se']:.2f} | [{r['ci95'][0]:+.2f}, {r['ci95'][1]:+.2f}] | "
              f"{r['p']:.4f} | {'reject H0' if rej else 'n.s.'} | {'yes' if equiv else 'no'} | {r['corr']:.2f} |")


if __name__ == "__main__":
    main()
