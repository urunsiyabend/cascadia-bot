# Preregistration: strategic re-evaluation in Cascadia (Phase 1, confirmatory)

**Status:** draft, revision 1, for approval — *no confirmatory game has been played.*
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

## 4. Conditions and design

### 4.1 Conditions (primary)

Compute unit: placements simulated inside rollouts per game ("simulated decisions"). The reference budget is
"evaluate every turn with 6 rollouts per plan". Sample counts of the other conditions were set by
`experiments/replanning/budget.py`. A development check (4 games per condition, seeds 900000–900001, outside
the confirmatory range; only budget and time inspected) matched the theoretical budgets exactly:

| Label | Spec | Evaluations/game | Rollouts/plan | Simulated decisions/game (theory / dev. measured) | s/game (dev.) |
|---|---|---|---|---|---|
| NEVER | `plan:replan=never,samples=62` | 1 | 62 | 26,939 / 26,939 | 16.8 |
| EV-1 | `plan:replan=ev,check_every=1,samples=6` | 19 | 6 | 26,961 / 26,961 | 20.0 |
| EV-3 | `plan:replan=ev,check_every=3,samples=16` | 7 | 16 | 26,488 / 26,488 | 20.4 |
| ALWAYS-1 | `plan:replan=always,check_every=1,samples=6` | 19 | 6 | 26,961 / 26,961 | 19.9 |
| ALWAYS-3 | `plan:replan=always,check_every=3,samples=16` | 7 | 16 | 26,488 / 26,488 | 20.0 |

`never` has no re-evaluation frequency, so it appears once; it spends the whole budget on the initial choice.

### 4.2 Equal total budget, different temporal allocation

The conditions are matched on the **total** compute per game, not on its timing. Re-evaluation frequency is
therefore a manipulation of *when* compute is spent and of *how precise each evaluation is*: every-turn
conditions make 19 evaluations with 6 rollouts per plan, every-3-turns conditions 7 evaluations with 16, and
NEVER a single evaluation with 62 at the start. Expected share of the budget by own-turn window (theory):

| Condition | turns 0–6 | turns 7–12 | turns 13–18 |
|---|---|---|---|
| NEVER | 100% | 0% | 0% |
| EV-1, ALWAYS-1 | 57% | 30% | 12% |
| EV-3, ALWAYS-3 | 67% | 25% | 9% |

(Later rollouts are shorter, so most compute falls early even for every-turn evaluation.) The four-game
development check is **not** taken as proof of equal budgets: every confirmatory game records its simulated
decisions and the per-evaluation log (`bot_stats.sim_decisions`, `bot_stats.eval_log`), and the analysis
reports, per condition, the mean, SD, minimum, 5th/95th percentiles and maximum of the per-game budget and the
realised temporal distribution. Manipulation check: each condition's mean budget lies within ±3% of the
reference (26,961; secondary ×3 conditions: 80,883). A failed check is reported as a deviation; no games are
excluded.

### 4.3 Randomness and reproducibility

The engine has one draw RNG per game (`Game._rng`, seeded with the game seed). It fixes, in this order, the
scoring cards, the starter tiles and the complete tile order (the tile stack is shuffled once at setup), and
then serves every token draw during play. Agents never use it: they simulate on copies with resampled hidden
information and their own RNGs (`Game.determinize`); bot seeds are `10·seed + seat`.
`experiments/replanning/check_rng.py` verified (development seeds 3,100,000+):

1. **Isolation:** 9 agent types (including all PlanBot variants, MCE, MCTS, lookahead, nature-token wipes)
   never changed the draw-RNG state or any game state while deciding.
2. **Determinism:** the same seed and configuration reproduce the identical game (every placement and score)
   in-process, in fresh processes with PYTHONHASHSEED 0 vs 12345, and with 1 vs 2 worker processes.
3. **A shared seed does not guarantee identical random conditions.** Across two different agents with the
   same seed (30 seeds), cards, starters, the initial display and the full tile order were identical in 100%
   of games, but token draws depend on the bag contents and therefore on the agents' choices: on average the
   first ≈ 39 drawn tokens were identical and ≈ 90% of draw positions matched over the game; the sequences
   diverge after differing wipes or returned tokens. A "presorted" token order (bag shuffled once, returns
   reinserted at random positions) did not increase this agreement (89%), so the confirmatory runs use the
   default `token_order=random`. Pairing by seed therefore controls cards, starters and tiles fully and tokens
   partially; the analysis does not assume more.

`check_rng.py` is re-run at the frozen commit before the first confirmatory run; any failure stops the study.

### 4.4 Design

Every condition plays 800 games against `greedy`: seeds 1,000,000–1,000,399, each with both seat orders
(`python -m cascadia_bot.sweep --seed 1000000 --games 800`). All conditions use the identical 400 seeds and
both seat orders. **The independent sampling unit is the seed**: the two seat-order games of a seed share
cards, starters and tile order and are averaged into one seed-level observation before any test or bootstrap.
Scripts: `experiments/replanning/run_primary.sh <LABEL>`.

## 5. Outcomes and primary analysis

### 5.1 Outcome, estimands and contrasts

* **Outcome:** per-game score difference *d* = agent total − greedy total; seed-level outcome
  *D* = mean of *d* over the two seat orders of the seed.
* **Primary contrasts:** estimate = mean over the 400 seeds of *D_A − D_B*.

| Contrast | A − B | Role | Expected direction (exploratory data) |
|---|---|---|---|
| **C1** | ALWAYS-1 − ALWAYS-3 | **Main question, frequency:** effect of re-evaluating every turn rather than every third turn, at equal total budget and fixed rule | positive |
| C2 | EV-1 − EV-3 | frequency under the `ev` rule | none |
| C3 | ALWAYS-1 − NEVER | total effect of the flexible every-turn policy versus one upfront choice | positive |
| C4 | ALWAYS-1 − EV-1 | switching rule, every turn | none |
| **C5** | ALWAYS-3 − EV-3 | **Main question, rule:** effect of always adopting the best estimate rather than switching only on statistical evidence, at equal frequency and budget | positive |

**Interpretation limits.** C1 and C5 answer RQ1 directly (one factor varied, the other and the budget held
fixed); C2 and C4 complete the 2 × 2 rule × frequency design. **C3 is not an isolated commitment effect:**
ALWAYS-1 and NEVER differ in the switching rule, in the number and precision of evaluations (19 × 6 vs 1 × 62
rollouts per plan) and in the temporal allocation of compute, and NEVER still adapts at the move level and in
its focus habitat. C3 is reported as the total effect of these policy differences.

### 5.2 Tests and multiplicity

* **Superiority family:** for each contrast H0: Δ = 0, two-sided z test on the seed-level differences
  (n = 400), Holm–Bonferroni over C1–C5 at family-wise α = 0.05.
* **Equivalence family:** for each contrast H0: |Δ| ≥ SESOI, TOST with p = max of the two one-sided p-values,
  Holm–Bonferroni over C1–C5 at family-wise α = 0.05 (a separate, pre-specified family; the two families each
  control their own family-wise error rate).
* **Estimation:** 95% percentile bootstrap CI resampling seeds (10,000 resamples, RNG seed 12345).
* **Joint classification** (both outcomes can occur together when an effect is small but precise):

| Superiority rejected | Equivalence rejected | Classification |
|---|---|---|
| yes | no | *supported* (expected sign) / *contradicted* (opposite sign); for C2, C4: *difference* with its sign |
| yes | yes | *detectable but practically negligible* (|Δ| < SESOI) |
| no | yes | *practically equivalent* |
| no | no | *inconclusive* |

### 5.3 Smallest effect size of interest (SESOI = ±0.5 points per game)

0.5 points per game is about 2.8 percentage points of win rate (exploratory slope ≈ 5.7 pp per point), half
a scoring unit per game, and smaller than the smallest agent-design improvement we treated as meaningful in
the exploratory work (value model v2 over v1: +0.67 ± 0.27). Differences below 0.5 points per game would not
change which agent design we recommend.

**Feasibility (from the variance pilot, section 7):** with 400 seeds the 90% CI half-width is ≈ 0.62 points,
wider than the ±0.5 margin, so **equivalence at ±0.5 cannot be concluded at this sample size even if the
true effect is zero** (TOST power ≈ 0). The equivalence family is kept so that every result is classified
honestly, but in practice it can only return "not equivalent". Options for approval: keep ±0.5 as is;
widen the SESOI to ±1.0 (TOST power at Δ = 0 ≈ 64–69% at α = 0.05, 18–27% at α = 0.01 with 400 seeds;
86–90% / 58–65% with 600 seeds); or increase the sample.

### 5.4 Code

`experiments/replanning/analyze.py`, written before any confirmatory data and tested on synthetic data only.
It refuses data with duplicated games or seeds missing a seat order, and prints the condition table,
budget distributions, temporal allocation, both test families with the joint classification, and the
secondary analyses.

## 6. Secondary analyses (pre-specified, outside the confirmatory families)

1. Win share per condition (ties count as fractions); plan switches per game.
2. Budget distributions and temporal allocation (section 4.2).
3. **S3, rule × frequency interaction** = C1 − C2 (seed level, unadjusted).
4. **Budget sensitivity:** `EV-1x3` (`plan:replan=ev,check_every=1,samples=18`) and `ALWAYS-1x3`
   (`plan:replan=always,check_every=1,samples=18`), 400 games each on seeds 1,000,000–1,000,199 (both seat
   orders, a subset of the primary seeds); S1 = EV-1x3 − EV-1, S2 = ALWAYS-1x3 − ALWAYS-1, both test
   families with Holm within this secondary family. **Caveat:** the `ev` rule switches when the gap exceeds
   two standard errors of the rollout estimates; more rollouts shrink those standard errors, so S1 mixes
   better estimates with more frequent switching. Switch counts are reported to separate the two; `always`
   (S2) has no such threshold.

## 7. Sample size and power (seed blocks)

**Variance pilot** (`experiments/replanning/variance_pilot.py`): proxy agents `heuristic` and `value` against
`greedy`, 1,000 development seeds (3,300,000+) × 2 seat orders. These are not study conditions; the pilot
only estimates variance components.

| Quantity | heuristic | value |
|---|---|---|
| SD of per-game *d* | 8.24 | 8.01 |
| ρ_s, correlation of *d* between the two seat orders of a seed | −0.10 | −0.04 |
| SD of seed-level *D* | 5.52 | 5.54 |
| ρ_c, correlation of *D* between the two conditions on the same seeds | +0.08 | |
| SD of a paired seed-level contrast | 7.49 (pessimistic, ρ_c = 0: 7.82) | |

Seat orders within a seed are nearly independent, so seed blocking costs no precision; pairing across
conditions helps little (ρ_c ≈ 0.08). With 400 seeds the contrast SE is 0.37–0.39 and the power to detect a
true effect is:

| True effect | α = 0.01 (first Holm step) | α = 0.05 (last Holm step) |
|---|---|---|
| 1.0 point | 0.49–0.54 | 0.72–0.76 |
| 1.5 points | 0.90–0.92 | 0.97–0.98 |
| 2.0 points | 0.99–1.00 | 1.00 |

With 600 seeds (1,200 games per condition) the power for 1.0 point rises to 0.71–0.76 / 0.88–0.90.
Exploratory effects of interest are ≈ 1–4 points (C5 ≈ 1.0, which is the least powered contrast). The
proxy agents may have a different variance from PlanBot; the realised SEs are reported.

**Runtime** (4 workers): primary ≈ 63 min per condition (≈ 5.3 h); secondary ≈ 95 min per condition (≈ 3.2 h).

## 8. Data handling

* No game is excluded. Each condition runs in one invocation; a crashed or interrupted run is discarded and
  re-run in full (identical seeds give identical games, section 4.3).
* Raw per-game records (seeds, seats, scores, winners, compute, plan logs, token order) are committed under
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
* Results concern preference re-evaluation with this plan representation and these bonuses, in two-player
  games.
* Seed pairing controls cards, starters and tile order but only partially the token draws (section 4.3).

## 11. Changes to this document

* Revision 1 (before any confirmatory run): seed as the independent unit with seed-block bootstrap and a
  seed-level power analysis from a variance pilot; per-game budget recording, budget-distribution and
  temporal-allocation reporting; randomness and reproducibility checks; separate Holm families for
  superiority and TOST with a joint classification; SESOI rationale and feasibility; C1/C5 as the main
  contrasts, C3 interpreted as a total policy effect; secondary rule × frequency interaction.

## 12. Phase 2 (planned, not preregistered here)

A blueprint agent whose plans are target end-state features (graded wildlife patterns per scoring card,
habitat targets, optional spatial anchors), keeping K candidate blueprints alive. Plan value will be
estimated as V(b, s) = E[S_final | s, π_b] by rollouts of the blueprint-following policy π_b (goals interact,
so per-goal expected gains are not summed); progress, completion probability and opportunity cost are
decision aids only. A further hypothesis: the value of commitment depends on the marginal return profile
ΔS(n) = S(n+1) − S(n) of the scoring cards, which will be computed per card before any Phase 2 experiment.
Phase 2 will be preregistered separately before it is run.
