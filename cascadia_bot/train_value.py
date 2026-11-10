"""Train the linear value model from self-play.

Every position of every game is recorded from every player's perspective with
target = final score - current score. A ridge regression is fitted on the
named features of :mod:`cascadia_bot.bots.features`; games are split into
train/holdout sets and the holdout R^2 is reported.

    python -m cascadia_bot.train_value --players 2 --games 4000 --workers 4

Writes ``cascadia_bot/models/value_<n>p.json`` (or ``--out``). Requires numpy.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from .bots import make_bot
from .bots.features import MODEL_DIR, LinearValue, game_features
from .game import Game, GameConfig
from .scoring import CARD_LETTERS, ScoringCards


def play_and_record(job: tuple[int, int, list[str], float]) -> list[tuple[dict, float, int]]:
    seed, n, specs, family_share = job
    rng = random.Random(seed)
    if rng.random() < family_share:
        cards = ScoringCards(mode=rng.choice(["family", "intermediate"]))
    else:
        cards = ScoringCards(cards=tuple(rng.choice(CARD_LETTERS) for _ in range(5)))  # type: ignore[arg-type]
    bots = [make_bot(rng.choice(specs), seed=seed * 10 + i) for i in range(n)]
    game = Game(GameConfig(num_players=n, seed=seed, cards=cards))
    pending: list[tuple[int, dict, int]] = []

    def record() -> None:
        totals = [s.total for s in game.scores()]
        for p in range(n):
            pending.append((p, game_features(game, p), totals[p]))

    record()
    while not game.game_over:
        bot = bots[game.current_player]
        for _ in range(8):
            action = bot.choose_pre_action(game)
            if action is None:
                break
            game.apply_pre_action(action)
        game.apply_placement(bot.choose_placement(game))
        if not game.game_over:
            record()
    final = [s.total for s in game.scores()]
    return [(f, float(final[p] - cur), seed) for p, f, cur in pending]


def fit(rows: list[tuple[dict, float, int]], ridge: float, holdout: float, seed: int):
    import numpy as np

    names = sorted({k for f, _, _ in rows for k in f})
    index = {k: i for i, k in enumerate(names)}
    games = sorted({g for _, _, g in rows})
    rnd = random.Random(seed)
    test_games = set(rnd.sample(games, max(1, int(len(games) * holdout))))

    def matrix(sel):
        X = np.zeros((len(sel), len(names)))
        y = np.zeros(len(sel))
        for r, (f, target, _) in enumerate(sel):
            for k, v in f.items():
                X[r, index[k]] = v
            y[r] = target
        return X, y

    train = [r for r in rows if r[2] not in test_games]
    test = [r for r in rows if r[2] in test_games]
    Xtr, ytr = matrix(train)
    Xte, yte = matrix(test)
    # Scale columns for a well-conditioned ridge, then unscale the weights.
    scale = np.maximum(np.abs(Xtr).max(axis=0), 1e-9)
    A = (Xtr / scale).T @ (Xtr / scale) + ridge * np.eye(len(names))
    b = (Xtr / scale).T @ ytr
    w = np.linalg.solve(A, b) / scale

    def r2(X, y):
        resid = y - X @ w
        return 1.0 - resid.var() / y.var()

    # Baseline: future gain predicted from time left only.
    tcols = [index[k] for k in ("bias", "t", "t2")]
    wb = np.linalg.lstsq(Xtr[:, tcols], ytr, rcond=None)[0]
    mse_time = float(((yte - Xte[:, tcols] @ wb) ** 2).mean())
    mse_model = float(((yte - Xte @ w) ** 2).mean())
    base_r2 = 1.0 - mse_time / yte.var()
    rmse = mse_model**0.5
    weights = {k: float(w[i]) for k, i in index.items() if abs(w[i]) > 1e-12}
    stats = {
        "train_rows": len(train),
        "test_rows": len(test),
        "r2_train": float(r2(Xtr, ytr)),
        "r2_test": float(r2(Xte, yte)),
        "r2_test_time_only": float(base_r2),
        "rmse_test": rmse,
        "rmse_test_time_only": mse_time**0.5,
        # share of the variance left by the time-only model that the features explain
        "skill_vs_time": 1.0 - mse_model / mse_time,
    }
    return weights, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train the linear value model from self-play.")
    ap.add_argument("--players", type=int, default=2)
    ap.add_argument("--games", type=int, default=3000)
    ap.add_argument("--policy", nargs="+", default=["heuristic", "greedy"], help="bot specs sampled per seat")
    ap.add_argument("--family-share", type=float, default=0.1, help="share of family/intermediate games")
    ap.add_argument("--ridge", type=float, default=1.0)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    jobs = [(args.seed + i, args.players, args.policy, args.family_share) for i in range(args.games)]
    rows: list = []
    t0 = time.time()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(play_and_record, jobs, chunksize=8)):
                rows.extend(r)
                if (i + 1) % 100 == 0:
                    print(f"\r{i + 1}/{len(jobs)} games ({time.time() - t0:.0f}s)", end="", file=sys.stderr)
    else:
        for i, job in enumerate(jobs):
            rows.extend(play_and_record(job))
            if (i + 1) % 100 == 0:
                print(f"\r{i + 1}/{len(jobs)} games ({time.time() - t0:.0f}s)", end="", file=sys.stderr)
    print(file=sys.stderr)

    weights, stats = fit(rows, args.ridge, args.holdout, args.seed)
    meta = {
        "players": args.players,
        "games": args.games,
        "policy": args.policy,
        "family_share": args.family_share,
        "ridge": args.ridge,
        **stats,
    }
    out = args.out or str(MODEL_DIR / f"value_{args.players}p.json")
    MODEL_DIR.mkdir(exist_ok=True)
    LinearValue(weights, meta).save(out)
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()})
    print(f"saved {len(weights)} weights to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
