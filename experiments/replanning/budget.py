"""Compute budget matching for the replanning confirmatory study.

Budget unit: placements simulated inside plan-evaluation rollouts per game
("simulated decisions"). A rollout started at our own turn t (t turns already
played, 2 players) simulates our remaining 20 - t placements plus the
opponent's remaining 20 - t (we are seat 0) or 19 - t (seat 1): on average
39.5 - 2t. Every evaluation runs ``n`` rollouts for each of the 11 candidate
plans. Plans are re-evaluated on own turns t = 0, k, 2k, ... <= 18 (no update on
the last turn).

    python experiments/replanning/budget.py
"""

PLANS = 11
LAST_EVAL_TURN = 18


def decisions_per_rollout(t: int) -> float:
    return (20 - t) + (20 - t - 0.5)


def eval_turns(check_every: int | None) -> list[int]:
    if check_every is None:  # never: a single evaluation on the first turn
        return [0]
    return list(range(0, LAST_EVAL_TURN + 1, check_every))


def budget(check_every: int | None, samples: int) -> float:
    return PLANS * samples * sum(decisions_per_rollout(t) for t in eval_turns(check_every))


def matched_samples(check_every: int | None, reference: float) -> int:
    per_sample = budget(check_every, 1)
    return max(1, round(reference / per_sample))


if __name__ == "__main__":
    for base in (6, 18):
        ref = budget(1, base)
        print(f"reference: check every turn with {base} rollouts/plan -> {ref:.0f} simulated decisions per game")
        for label, every in (("every turn", 1), ("every 3 turns", 3), ("never (single evaluation)", None)):
            n = matched_samples(every, ref)
            b = budget(every, n)
            print(f"  {label:26s} evaluations {len(eval_turns(every)):2d}  samples {n:3d}  budget {b:7.0f}"
                  f"  ({100 * (b / ref - 1):+.1f}%)")
