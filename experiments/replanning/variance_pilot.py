"""Variance pilot for the seed-block power analysis (preregistration section 7).

Uses two fast proxy agents (`heuristic`, `value`) instead of the study conditions,
each against `greedy`, on development seeds 3,300,000+ (outside the confirmatory
range), both seat orders per seed. Estimates:

* sigma   - SD of the per-game score difference d = agent - greedy,
* rho_s   - correlation of d between the two seat orders of the same seed,
* sd_seed - SD of the seed-level mean of d (the analysis unit),
* rho_c   - correlation of seed-level d between two conditions on the same seeds,
* SE and minimum detectable effects of a paired seed-level contrast with 400 seeds.

    python experiments/replanning/variance_pilot.py [--seeds 1000] [--workers 4]
"""

from __future__ import annotations

import argparse
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cascadia_bot.arena import run_tournament  # noqa: E402

Z = {"0.01": 2.5758, "0.0125": 2.4977, "0.0167": 2.3940, "0.025": 2.2414, "0.05": 1.9600}
Z_POWER = 0.8416  # 80% power


def seed_level(spec: str, seeds: int, base: int, workers: int) -> tuple[dict[int, list[float]], float]:
    _, results = run_tournament([spec, "greedy"], 2 * seeds, base, None, True, False, workers)
    per_seed: dict[int, list[float]] = {}
    for r in results:
        me = r["seats"].index(spec)
        d = r["scores"][me]["total"] - r["scores"][1 - me]["total"]
        per_seed.setdefault(r["seed"], [None, None])[me] = d
    games = [d for v in per_seed.values() for d in v]
    return per_seed, st.stdev(games)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--base", type=int, default=3_300_000)
    args = ap.parse_args()

    data = {}
    for spec in ("heuristic", "value"):
        per_seed, sigma = seed_level(spec, args.seeds, args.base, args.workers)
        a = [v[0] for v in per_seed.values()]
        b = [v[1] for v in per_seed.values()]
        rho_s = st.correlation(a, b)
        means = {s: (v[0] + v[1]) / 2 for s, v in per_seed.items()}
        data[spec] = means
        print(f"{spec:10s} sigma(game) {sigma:5.2f}  rho_s (seat orders, same seed) {rho_s:+.3f}  "
              f"sd(seed mean) {st.stdev(means.values()):5.2f}  (independent games would give {sigma / math.sqrt(2):5.2f})")

    seeds = sorted(set(data["heuristic"]) & set(data["value"]))
    x = [data["heuristic"][s] for s in seeds]
    y = [data["value"][s] for s in seeds]
    rho_c = st.correlation(x, y)
    diff = [b - a for a, b in zip(x, y)]
    sd_c = st.stdev(diff)
    print(f"between conditions: rho_c (seed means) {rho_c:+.3f}; SD of paired seed-level contrast {sd_c:.2f}")

    print("\nPower with 400 seeds (seed-level paired contrast, 80% power):")
    for label, sd in (("pilot estimate", sd_c),
                      ("pessimistic (rho_c = 0)", math.sqrt(st.variance(x) + st.variance(y)))):
        se = sd / math.sqrt(400)
        mde = {k: (z + Z_POWER) * se for k, z in Z.items()}
        tost_half = 1.6449 * se
        print(f"  {label:25s} SD {sd:5.2f} -> SE {se:.2f}; MDE alpha=.01 {mde['0.01']:.2f}, "
              f"alpha=.0125 {mde['0.0125']:.2f}, alpha=.0167 {mde['0.0167']:.2f}, alpha=.025 {mde['0.025']:.2f}, "
              f"alpha=.05 {mde['0.05']:.2f}; 90% CI half-width {tost_half:.2f}")


if __name__ == "__main__":
    main()
