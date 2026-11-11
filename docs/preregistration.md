# Preregistration: strategic re-evaluation in Cascadia (Phase 1, confirmatory)

**Status:** draft for approval — *no confirmatory game has been played.*
**Frozen at:** the commit that adds this file (the run scripts record the exact commit of every run in
`results/replanning/runs.jsonl`). Any later change to this document is listed in section 11.

## 1. Scope and claims

All experiments run before this document (H1–H7, the plan-layer sweeps, MCE sweeps and league, value-model
experiments; see `README.md`) are **exploratory**. They generated the hypotheses below and are reported as
exploratory results only.

The agents studied here do **not** plan towards a target end state. A "plan" is a *strategic preference*:
two focus animals (or none) that bias move selection; the focus habitat is the player's currently largest
corridor and is re-derived on every move even under `never`, and every agent reacts to new draws at the move
level. The confirmatory claims are therefore about **how often strategic preferences are re-evaluated and
under which switching rule**, not about long-term planning in general:

> **RQ1.** With compute held constant, how do the re-evaluation frequency and the switching rule of strategic
> preferences affect agent performance in two-player Cascadia?

Long-term, end-state ("blueprint") planning is Phase 2 (section 12) and will be preregistered separately.

## 2. Exploratory evidence that motivated the hypotheses

Two players, score difference per game against `greedy`, same 400 seeds per row (SE = standard error):

| Agent (exploratory) | Rollouts/plan | Evaluations/game | Score diff ± SE | Win | s/game |
|---|---|---|---|---|---|
| `plan:replan=never` | 6 | 1 | −0.81 ± 0.45 | 46.0% | 1.6 |
| `plan` (`ev`, every 3 turns) | 6 | 7 | +0.32 ± 0.44 | 52.4% | 7.2 |
| `plan:z=1,min_gap=0` | 6 | 7 | +0.47 ± 0.42 | 50.7% | 7.6 |
| `plan:replan=always` (every 3 turns) | 6 | 7 | +1.30 ± 0.41 | 58.0% | 7.1 |
| `plan:replan=always,check_every=1` | 6 | 19 | +3.50 ± 0.40 | 70.4% | 20.1 |

Known weaknesses of this evidence: unequal compute between frequencies (the every-turn agent used ~2.8×
the time of the every-3-turns agents), many comparisons, and no correction for multiplicity.

## 3. Environment and agents

* Engine: `cascadia_bot` at the frozen commit; two players; standard scoring with one A–D card per wildlife
  drawn at random from the game seed; habitat majorities on.
* Opponent: `greedy` with default parameters (also the opponent model inside all rollouts).
* Agent: `PlanBot` (`cascadia_bot/bots/plan.py`). Candidate plans: the 10 pairs of animals and "no plan".
  Move value = greedy value + plan bonus (+1.5 focus token, +0.5 keep a new focus-compatible tile free,
  −1.0 block a focus-compatible tile with another token, +0.5 per tile of focus-corridor growth).
  Plan value = mean final own score of `samples` full-game rollouts per plan from the current state
  (hidden information resampled; all plans share the same rollout seeds). Plans are evaluated on own turns
  t = 0, k, 2k, … ≤ 18.
* Switching rules: `never` (plan chosen at t = 0 is kept), `ev` (switch to the best alternative only if it
  beats the current plan by > 1 point **and** by > 2 standard errors of the difference), `always` (switch to
  the plan with the best estimate at every evaluation).

## 4. Conditions (primary)

Compute unit: placements simulated inside rollouts per game ("simulated decisions"). The reference budget is
"evaluate every turn with 6 rollouts per plan". Sample counts of the other conditions were set by
`experiments/replanning/budget.py`; budgets were verified on 4 development games per condition (seeds
900000–900001, outside the confirmatory range; only budget and time were inspected):

| Label | Spec | Evaluations/game | Rollouts/plan | Simulated decisions/game (theory / measured) | s/game (dev.) |
|---|---|---|---|---|---|
| NEVER | `plan:replan=never,samples=62` | 1 | 62 | 26,939 / 26,939 | 16.8 |
| EV-1 | `plan:replan=ev,check_every=1,samples=6` | 19 | 6 | 26,961 / 26,961 | 20.0 |
| EV-3 | `plan:replan=ev,check_every=3,samples=16` | 7 | 16 | 26,488 / 26,488 | 20.4 |
| ALWAYS-1 | `plan:replan=always,check_every=1,samples=6` | 19 | 6 | 26,961 / 26,961 | 19.9 |
| ALWAYS-3 | `plan:replan=always,check_every=3,samples=16` | 7 | 16 | 26,488 / 26,488 | 20.0 |

`never` has no re-evaluation frequency, so it appears once; it spends the whole budget on the initial
choice (a stronger start than the exploratory `never`).

**Design.** Every condition plays 800 games against `greedy`: seeds 1,000,000–1,000,399, each with both seat
orders (`python -m cascadia_bot.sweep --seed 1000000 --games 800`). All conditions use identical seeds and
seat orders, so games are **paired across conditions by (seed, agent seat)**. Bot seeds are `10·seed + seat`.
Runs are deterministic given the commit. Scripts: `experiments/replanning/run_primary.sh <LABEL>`.

## 5. Outcomes and primary analysis

* **Primary outcome:** per-game score difference *d* = agent total − greedy total.
* **Primary contrasts** (estimate = mean over paired games of *d_A − d_B*):

| Contrast | A − B | Question | Expected direction (from exploratory data) |
|---|---|---|---|
| C1 | ALWAYS-1 − ALWAYS-3 | frequency, under `always` | positive |
| C2 | EV-1 − EV-3 | frequency, under `ev` | none |
| C3 | ALWAYS-1 − NEVER | flexible vs committed preference | positive |
| C4 | ALWAYS-1 − EV-1 | switching rule, every turn | none |
| C5 | ALWAYS-3 − EV-3 | switching rule, every 3 turns | positive |

* **Test:** two-sided z test on the paired differences (n = 800; normal approximation), 95% percentile
  bootstrap CI (10,000 resamples, seed 12345). **Multiplicity:** Holm–Bonferroni over C1–C5, family-wise
  α = 0.05.
* **Equivalence:** smallest effect size of interest (SESOI) ±0.5 points per game; a contrast is called
  *practically equivalent* if its 90% CI lies within ±0.5 (TOST at α = 0.05).
* **Decision rule per contrast:** *supported* = Holm-significant with the expected sign; *contradicted* =
  Holm-significant with the opposite sign; *equivalent* = TOST criterion met; otherwise *inconclusive*.
  For C2 and C4 (no expected direction) we report the direction of any Holm-significant effect.
* Analysis code, written before any confirmatory data: `experiments/replanning/analyze.py`
  (tested on synthetic data only). It rejects data sets with duplicated or unpaired games.

## 6. Secondary analyses (pre-specified, reported separately, not part of the confirmatory family)

1. Win share per condition and per contrast (ties count as fractions).
2. Plan switches per game and simulated decisions per game (manipulation check: budgets within ±3%).
3. **Budget sensitivity:** `EV-1x3` (`plan:replan=ev,check_every=1,samples=18`) and `ALWAYS-1x3`
   (`plan:replan=always,check_every=1,samples=18`), 400 games each on seeds 1,000,000–1,000,199 (both seat
   orders, a subset of the primary games). Contrasts S1 = EV-1x3 − EV-1, S2 = ALWAYS-1x3 − ALWAYS-1, Holm
   within this family. **Caveat:** the `ev` threshold uses the standard error of the rollout estimates, which
   shrinks with more rollouts, so S1 mixes better estimates with more frequent switching. Switch counts are
   reported to separate the two; `always` (S2) has no such threshold.

## 7. Sample size

Exploratory per-game SD of *d* ≈ 8.4 points. The SD of a paired contrast is √(2·8.4²·(1−ρ)) with unknown
correlation ρ between conditions on the same seed. With 800 games per condition (80% power):

| ρ | SE of contrast | Minimum detectable effect, α = 0.01 (first Holm step) | α = 0.05 (last step) |
|---|---|---|---|
| 0.0 | 0.42 | 1.44 points | 1.18 points |
| 0.3 | 0.35 | 1.20 points | 0.98 points |

The exploratory effects of interest are ~1–4 points. 1,200 games would lower the detectable effect to
~0.96–1.17 points at ~1.5× the runtime; 800 is chosen as the trade-off.

**Runtime estimate** (4 workers): primary ≈ 63 min per condition (≈ 5.3 h total); secondary ≈ 95 min per
condition (≈ 3.2 h total).

## 8. Data handling

* No game is excluded. Each condition is run in one invocation; a crashed or interrupted run is discarded
  and re-run in full (identical seeds give identical games).
* Raw per-game records (seeds, seats, scores, winners, compute, plan logs) are committed under
  `results/replanning/`, with the commit hash of every run in `runs.jsonl`.
* If a bug affecting the agents or the engine is found after the runs, it is fixed, **all** conditions are
  re-run, and both results are reported, with the change logged in section 11.

## 9. Exploratory follow-ups

Any analysis not listed in sections 5–6 (e.g. effects per scoring card, per game phase, per seat) is labelled
exploratory in all reports.

## 10. Limitations stated in advance

* Opponents and rollout opponents are both `greedy`, so the agents' opponent model is exact; results may not
  transfer to other opponents.
* Plan values come from noisy rollouts (exploratory SE 1–5 points per plan at 6 rollouts).
* Results concern preference re-evaluation with this plan representation and these bonuses.

## 11. Changes to this document

* (none yet)

## 12. Phase 2 (planned, not preregistered here)

A blueprint agent whose plans are target end-state features (graded wildlife patterns per scoring card,
habitat targets, optional spatial anchors), keeping K candidate blueprints alive. Plan value will be
estimated as V(b, s) = E[S_final | s, π_b] by rollouts of the blueprint-following policy π_b (goals interact,
so per-goal expected gains are not summed); progress, completion probability and opportunity cost are
decision aids only. A further hypothesis: the value of commitment depends on the marginal return profile
ΔS(n) = S(n+1) − S(n) of the scoring cards, which will be computed per card before any Phase 2 experiment.
Phase 2 will be preregistered separately before it is run.
