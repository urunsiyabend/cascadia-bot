"""Pre-specified analysis for the replanning confirmatory study (docs/preregistration.md).

Input: per-game records written by ``python -m cascadia_bot.sweep --games-out``.
Every condition plays the same seeds with both seat orders against ``greedy``.

Unit of analysis: the **seed** (the two seat-order games of a seed are averaged),
so contrasts and bootstrap resampling use seed blocks, never individual games.

    python experiments/replanning/analyze.py results/replanning/primary_games.jsonl
    python experiments/replanning/analyze.py results/replanning/primary_games.jsonl \\
        --secondary results/replanning/secondary_games.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
from collections import defaultdict
from statistics import NormalDist

PRIMARY = {
    "NEVER": "plan:replan=never,samples=62",
    "EV-1": "plan:replan=ev,check_every=1,samples=6",
    "EV-3": "plan:replan=ev,check_every=3,samples=16",
    "ALWAYS-1": "plan:replan=always,check_every=1,samples=6",
    "ALWAYS-3": "plan:replan=always,check_every=3,samples=16",
}
PRIMARY_CONTRASTS = [  # (name, A, B): estimate of A - B (seed level)
    ("C1 frequency (always)", "ALWAYS-1", "ALWAYS-3"),
    ("C2 frequency (ev)", "EV-1", "EV-3"),
    ("C3 always-every-turn vs never", "ALWAYS-1", "NEVER"),
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
REFERENCE_BUDGET = {"x1": 26961, "x3": 80883}  # simulated decisions per game (budget.py)
BUDGET_TOLERANCE = 0.03
ALPHA = 0.05
SESOI = 0.5  # points per game (see preregistration section 5.3)
BOOTSTRAP = 10000
PHASES = ((0, 6), (7, 12), (13, 18))  # own-turn windows for the temporal budget report
_N = NormalDist()


def load(paths: list[str], conditions: dict[str, str]) -> dict[str, dict[int, dict]]:
    """label -> seed -> {"d": [d_seat0, d_seat1], "games": [...]}; checks uniqueness and completeness."""
    by_spec = {spec: label for label, spec in conditions.items()}
    seen: set[tuple[str, int, int]] = set()
    data: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"d": [None, None], "games": [None, None]}))
    for path in paths:
        for line in open(path):
            r = json.loads(line)
            label = by_spec.get(r["spec"])
            if label is None:
                continue
            seat = r["seats"].index(r["spec"])
            key = (label, r["seed"], seat)
            if key in seen:
                raise SystemExit(f"duplicate game {key}: every (condition, seed, seat) must appear once")
            seen.add(key)
            totals = [s["total"] for s in r["scores"]]
            stats = (r.get("bot_stats") or [{}, {}])[seat]
            entry = data[label][r["seed"]]
            entry["d"][seat] = totals[seat] - totals[1 - seat]
            entry["games"][seat] = {
                "win": (1.0 / len(r["winners"])) if seat in r["winners"] else 0.0,
                "switches": stats.get("switches"),
                "sim": stats.get("sim_decisions"),
                "eval_log": stats.get("eval_log") or [],
                "sec": r["seconds"][seat],
            }
    for label, seeds in data.items():
        for seed, e in seeds.items():
            if None in e["d"]:
                raise SystemExit(f"{label}: seed {seed} lacks one seat order")
    return data


def seed_means(seeds: dict[int, dict]) -> dict[int, float]:
    return {s: (e["d"][0] + e["d"][1]) / 2 for s, e in seeds.items()}


def describe(label: str, seeds: dict[int, dict]) -> str:
    m = list(seed_means(seeds).values())
    games = [g for e in seeds.values() for g in e["games"]]
    se = st.stdev(m) / math.sqrt(len(m))
    rho_s = st.correlation([e["d"][0] for e in seeds.values()], [e["d"][1] for e in seeds.values()])
    sw = [g["switches"] for g in games if g["switches"] is not None]
    return (f"| {label} | {len(m)} | {st.fmean(m):+.2f} ± {se:.2f} | {100 * st.fmean(g['win'] for g in games):.1f}% | "
            f"{st.fmean(sw) if sw else float('nan'):.2f} | {rho_s:+.2f} | {st.fmean(g['sec'] for g in games):.1f} |")


def budget_report(label: str, seeds: dict[int, dict]) -> tuple[str, str, bool]:
    games = [g for e in seeds.values() for g in e["games"]]
    sims = sorted(g["sim"] for g in games if g["sim"] is not None)
    if not sims:
        return f"| {label} | – | – | – | – | – |", f"| {label} | – | – | – |", True
    q = lambda p: sims[min(len(sims) - 1, int(p * len(sims)))]  # noqa: E731
    mean = st.fmean(sims)
    dev = mean / REFERENCE_BUDGET["x3" if label.endswith("x3") else "x1"] - 1
    ok = abs(dev) <= BUDGET_TOLERANCE
    line = (f"| {label} | {mean:,.0f} ({100 * dev:+.1f}%) | {st.stdev(sims):,.0f} | {sims[0]:,} / {q(0.05):,} / "
            f"{q(0.95):,} / {sims[-1]:,} | {'ok' if ok else 'OUT OF TOLERANCE'} |")
    share = []
    for lo, hi in PHASES:
        spent = sum(n for g in games for t, n in g["eval_log"] if lo <= t <= hi)
        share.append(spent)
    total = sum(share) or 1
    temporal = f"| {label} | " + " | ".join(f"{100 * s / total:.0f}%" for s in share) + " |"
    return line, temporal, ok


def contrast(a: dict[int, dict], b: dict[int, dict], rng: random.Random, subset_ok: bool) -> dict:
    ma, mb = seed_means(a), seed_means(b)
    seeds = sorted(set(ma) & set(mb))
    if subset_ok:
        if len(seeds) != min(len(ma), len(mb)):
            raise SystemExit("secondary seeds are not a subset of the primary seeds")
    elif len(seeds) != len(ma) or len(seeds) != len(mb):
        raise SystemExit("conditions are not played on identical seed sets")
    d = [ma[s] - mb[s] for s in seeds]
    n = len(d)
    mean = st.fmean(d)
    se = st.stdev(d) / math.sqrt(n)
    p_sup = 2 * (1 - _N.cdf(abs(mean) / se))  # H0: delta = 0
    p_tost = max(1 - _N.cdf((mean + SESOI) / se), _N.cdf((mean - SESOI) / se))  # H0: |delta| >= SESOI
    boots = sorted(st.fmean(rng.choices(d, k=n)) for _ in range(BOOTSTRAP))  # resampling seed blocks
    ci95 = (boots[int(0.025 * BOOTSTRAP)], boots[int(0.975 * BOOTSTRAP) - 1])
    rho_c = st.correlation([ma[s] for s in seeds], [mb[s] for s in seeds])
    return {"n": n, "mean": mean, "se": se, "p_sup": p_sup, "p_tost": p_tost, "ci95": ci95, "rho_c": rho_c}


def holm(ps: list[float], alpha: float) -> list[bool]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    reject = [False] * len(ps)
    for rank, i in enumerate(order):
        if ps[i] > alpha / (len(ps) - rank):
            break
        reject[i] = True
    return reject


def classify(sup: bool, equiv: bool, mean: float, expected: int | None) -> str:
    if sup and equiv:
        return "detectable but practically negligible"
    if equiv:
        return "practically equivalent"
    if sup:
        if expected is None:
            return f"difference ({'A > B' if mean > 0 else 'A < B'})"
        return "supported" if (mean > 0) == (expected > 0) else "contradicted"
    return "inconclusive"


EXPECTED = {"C1 frequency (always)": +1, "C3 always-every-turn vs never": +1, "C5 rule (every 3 turns)": +1}


def report_contrasts(title: str, results: list[tuple[str, dict]]) -> None:
    sup = holm([r["p_sup"] for _, r in results], ALPHA)
    eq = holm([r["p_tost"] for _, r in results], ALPHA)
    print(f"\n{title}: superiority family (Holm, FWER {ALPHA}) and equivalence family "
          f"(TOST, SESOI ±{SESOI}, Holm, FWER {ALPHA}); unit = seed")
    print("| Contrast | Seeds | Estimate (A−B) ± SE | 95% seed-block bootstrap CI | p (≠0) | Holm | p (TOST) | Holm | "
          "Classification | ρ_c |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (name, r), s, e in zip(results, sup, eq):
        print(f"| {name} | {r['n']} | {r['mean']:+.2f} ± {r['se']:.2f} | [{r['ci95'][0]:+.2f}, {r['ci95'][1]:+.2f}] | "
              f"{r['p_sup']:.4f} | {'reject' if s else 'n.s.'} | {r['p_tost']:.4f} | {'reject' if e else 'n.s.'} | "
              f"{classify(s, e, r['mean'], EXPECTED.get(name))} | {r['rho_c']:+.2f} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("primary")
    ap.add_argument("--secondary", help="games of the budget-sensitivity conditions")
    args = ap.parse_args()
    rng = random.Random(12345)

    conditions = dict(PRIMARY)
    paths = [args.primary]
    if args.secondary:
        conditions.update(SECONDARY)
        paths.append(args.secondary)
    data = load(paths, conditions)

    print("| Condition | Seeds | Seed-level score diff vs greedy (± SE) | Win share | Switches/game | ρ_s | s/game |")
    print("|---|---|---|---|---|---|---|")
    for label in conditions:
        if label in data:
            print(describe(label, data[label]))

    print("\nCompute budget per game (simulated decisions; reference "
          f"{REFERENCE_BUDGET['x1']:,} primary / {REFERENCE_BUDGET['x3']:,} for x3, "
          f"tolerance ±{100 * BUDGET_TOLERANCE:.0f}%)")
    print("| Condition | Mean (deviation) | SD | Min / 5% / 95% / Max | Check |")
    print("|---|---|---|---|---|")
    temporal = []
    for label in conditions:
        if label in data:
            line, temp, _ = budget_report(label, data[label])
            print(line)
            temporal.append(temp)
    print("\nTemporal distribution of the budget (share spent in own turns " +
          ", ".join(f"{lo}–{hi}" for lo, hi in PHASES) + ")")
    print("| Condition | " + " | ".join(f"turns {lo}–{hi}" for lo, hi in PHASES) + " |")
    print("|---|" + "---|" * len(PHASES))
    for t in temporal:
        print(t)

    primary = [(n, contrast(data[a], data[b], rng, False)) for n, a, b in PRIMARY_CONTRASTS]
    report_contrasts("Primary contrasts", primary)

    # Secondary (pre-specified, outside the confirmatory family)
    ma = {k: seed_means(data[k]) for k in ("ALWAYS-1", "ALWAYS-3", "EV-1", "EV-3")}
    seeds = sorted(ma["ALWAYS-1"])
    inter = [(ma["ALWAYS-1"][s] - ma["ALWAYS-3"][s]) - (ma["EV-1"][s] - ma["EV-3"][s]) for s in seeds]
    se = st.stdev(inter) / math.sqrt(len(inter))
    print(f"\nSecondary S3 interaction rule x frequency = C1 − C2: {st.fmean(inter):+.2f} ± {se:.2f} "
          f"(p = {2 * (1 - _N.cdf(abs(st.fmean(inter)) / se)):.4f}, unadjusted)")
    if args.secondary:
        sec = [(n, contrast(data[a], data[b], rng, True)) for n, a, b in SECONDARY_CONTRASTS]
        report_contrasts("Secondary budget-sensitivity contrasts", sec)


if __name__ == "__main__":
    main()
