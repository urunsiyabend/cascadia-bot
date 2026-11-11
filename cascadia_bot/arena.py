"""Tournament runner / CLI for comparing bots.

Examples::

    # 2-player match, 200 games, seats rotated, random scoring cards each game
    python -m cascadia_bot.arena greedy heuristic --games 200

    # 4-player game with fixed cards and 4 worker processes
    python -m cascadia_bot.arena greedy heuristic random lookahead --cards ABCDA --workers 4

    # Solo benchmark: each bot plays the same seeds alone
    python -m cascadia_bot.arena greedy heuristic --solo --games 100

    # Watch a single game
    python -m cascadia_bot.arena greedy heuristic --games 1 --show
"""

from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from .bots import make_bot
from .components import Habitat, Wildlife
from .game import GameConfig
from .render import render_game
from .runner import play_game
from .scoring import ScoringCards


@dataclass
class GameJob:
    seed: int
    specs: list[str]  # bot spec per seat
    cards: str | None  # None = random per game
    habitat_majority: bool


def _run_job(job: GameJob) -> dict:
    bots = [make_bot(spec, seed=job.seed * 10 + i) for i, spec in enumerate(job.specs)]
    cards = None if job.cards is None else ScoringCards.from_string(job.cards)
    config = GameConfig(num_players=len(bots), cards=cards, habitat_majority=job.habitat_majority, seed=job.seed)
    result = play_game(bots, config)
    return {
        "seed": job.seed,
        "cards": result.cards,
        "seats": job.specs,
        "scores": [s.as_dict() for s in result.scores],
        "winners": result.winners,
        "seconds": result.decision_seconds,
        "bot_stats": [bot.stats() if hasattr(bot, "stats") else {} for bot in bots],
    }


def build_jobs(specs: list[str], games: int, seed: int, cards: str | None, majority: bool, solo: bool) -> list[GameJob]:
    jobs = []
    if solo:
        for g in range(games):
            for spec in specs:
                jobs.append(GameJob(seed + g, [spec], cards, majority))
        return jobs
    n = len(specs)
    for g in range(games):
        block, rot = divmod(g, n)
        seats = specs[rot:] + specs[:rot]  # rotate seats so everyone starts equally often
        jobs.append(GameJob(seed + block, seats, cards, majority))
    return jobs


def summarize(results: list[dict], specs: list[str], solo: bool) -> dict:
    per: dict[str, dict] = {
        s: {"scores": [], "wins": 0.0, "games": 0, "seconds": 0.0, "wildlife": {}, "habitat": [], "nature": []}
        for s in specs
    }
    for r in results:
        winners = r["winners"]
        for seat, spec in enumerate(r["seats"]):
            sc = r["scores"][seat]
            d = per[spec]
            d["games"] += 1
            d["scores"].append(sc["total"])
            d["seconds"] += r["seconds"][seat]
            if not solo and seat in winners:
                d["wins"] += 1.0 / len(winners)
            for w, v in sc["wildlife"].items():
                d["wildlife"].setdefault(w, []).append(v)
            d["habitat"].append(sum(sc["habitat"].values()) + sum(sc["habitat_bonus"].values()))
            d["nature"].append(sc["nature_tokens"])
    summary = {}
    for spec, d in per.items():
        scores = d["scores"]
        if not scores:
            continue
        summary[spec] = {
            "games": d["games"],
            "mean": statistics.fmean(scores),
            "stdev": statistics.pstdev(scores),
            "min": min(scores),
            "max": max(scores),
            "win_rate": None if solo else d["wins"] / d["games"],
            "wildlife": {w: statistics.fmean(v) for w, v in d["wildlife"].items()},
            "habitat": statistics.fmean(d["habitat"]),
            "nature": statistics.fmean(d["nature"]),
            "sec_per_game": d["seconds"] / d["games"],
        }
    return summary


def format_summary(summary: dict, solo: bool) -> str:
    wl = [w.name.lower() for w in Wildlife]
    width = max([len(k) for k in summary] + [3]) + 2
    head = f"{'bot':<{width}}{'games':>6}{'mean':>8}{'sd':>6}{'min':>5}{'max':>5}"
    head += "" if solo else f"{'win%':>7}"
    head += "".join(f"{w[:4]:>6}" for w in wl) + f"{'hab':>6}{'nat':>5}{'s/game':>8}"
    lines = [head, "-" * len(head)]
    for spec, s in sorted(summary.items(), key=lambda kv: -kv[1]["mean"]):
        line = f"{spec:<{width}}{s['games']:>6}{s['mean']:>8.1f}{s['stdev']:>6.1f}{s['min']:>5}{s['max']:>5}"
        line += "" if solo else f"{100 * s['win_rate']:>6.1f}%"
        line += "".join(f"{s['wildlife'].get(w, 0):>6.1f}" for w in wl)
        line += f"{s['habitat']:>6.1f}{s['nature']:>5.1f}{s['sec_per_game']:>8.2f}"
        lines.append(line)
    return "\n".join(lines)


def run_tournament(specs: list[str], games: int = 100, seed: int = 0, cards: str | None = None,
                   habitat_majority: bool = True, solo: bool = False, workers: int = 1,
                   progress: bool = False) -> tuple[dict, list[dict]]:
    jobs = build_jobs(specs, games, seed, cards, habitat_majority, solo)
    results: list[dict] = []
    t0 = time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, r in enumerate(ex.map(_run_job, jobs, chunksize=max(1, len(jobs) // (workers * 8)))):
                results.append(r)
                if progress:
                    print(f"\r{i + 1}/{len(jobs)} games ({time.time() - t0:.0f}s)", end="", file=sys.stderr)
    else:
        for i, job in enumerate(jobs):
            results.append(_run_job(job))
            if progress:
                print(f"\r{i + 1}/{len(jobs)} games ({time.time() - t0:.0f}s)", end="", file=sys.stderr)
    if progress:
        print(file=sys.stderr)
    return summarize(results, list(dict.fromkeys(specs)), solo), results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Cascadia bot tournaments.")
    ap.add_argument("bots", nargs="+", help="bot specs, e.g. greedy  heuristic:potential_weight=0.5")
    ap.add_argument("--games", type=int, default=50, help="number of games (per bot in --solo)")
    ap.add_argument("--seed", type=int, default=0, help="base seed")
    ap.add_argument("--cards", default="random",
                    help="'random' (A-D per wildlife each game), 5 letters like ABCDA "
                         "(bear, elk, salmon, hawk, fox), 'family' or 'intermediate'")
    ap.add_argument("--no-majority", action="store_true", help="skip habitat majority bonuses")
    ap.add_argument("--solo", action="store_true", help="every bot plays solo games on the same seeds")
    ap.add_argument("--workers", type=int, default=1, help="parallel worker processes")
    ap.add_argument("--json", help="write per-game results + summary to this file")
    ap.add_argument("--show", action="store_true", help="print the final position of the first game")
    ap.add_argument("--plugin", action="append", default=[],
                    help="import this module first (e.g. one that calls cascadia_bot.bots.register)")
    args = ap.parse_args(argv)
    for module in args.plugin:
        importlib.import_module(module)

    if not args.solo and not 2 <= len(args.bots) <= 4:
        ap.error("a match needs 2-4 bots (use --solo for single-player benchmarks)")
    if len(set(args.bots)) != len(args.bots):
        ap.error("bot specs must be distinct (add a parameter to tell copies apart)")
    cards = None if args.cards == "random" else args.cards
    if cards is not None:
        ScoringCards.from_string(cards)  # validate early

    summary, results = run_tournament(args.bots, args.games, args.seed, cards, not args.no_majority,
                                      args.solo, args.workers, progress=True)
    print(format_summary(summary, args.solo))

    if args.show and results:
        r = results[0]
        bots = [make_bot(s, seed=r["seed"] * 10 + i) for i, s in enumerate(r["seats"])]
        cfg = GameConfig(num_players=len(bots), seed=r["seed"], habitat_majority=not args.no_majority,
                         cards=ScoringCards.from_string(r["cards"]))
        res = play_game(bots, cfg)
        print("\n" + render_game(res.game))
        for seat, (spec, sc) in enumerate(zip(r["seats"], res.scores)):
            hab = " ".join(f"{h.name[:3]}={sc.habitat[h]}+{sc.habitat_bonus[h]}" for h in Habitat)
            wild = " ".join(f"{w.name.lower()}={sc.wildlife[w]}" for w in Wildlife)
            print(f"seat {seat} {spec}: total {sc.total} | {wild} | {hab} | nature={sc.nature_tokens}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"summary": summary, "games": results}, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
