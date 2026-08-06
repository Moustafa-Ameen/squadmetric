# Recovery R2.2 — Separate Chip Projection Path

## Status

Implemented, runtime-hardened, and validated through the chip-aware
Champion/Challenger gate. The separate chip model is accepted as the R2
challenger configuration; production rollout remains a deliberate review
decision rather than an automatic side effect of the benchmark.

## Problem addressed

R2.1 introduced explicit transfer, captain, and chip model assignments, but it
only wired the captain override. A different chip model was rejected rather
than routed through the planner. That made consumer-specific model selection
incomplete and risked silently substituting a chip model for ordinary transfer
projections.

## Delivered

- `DeterministicBeamPlanner.decide` accepts separate current and future chip
  prediction frames.
- Ordinary transfer candidates and transfer-horizon gains continue to use the
  transfer prediction frames.
- Wildcard and Free Hit squad construction use the chip prediction frames.
- Bench Boost, Triple Captain, Assistant Manager, chip horizons, uncertainty,
  and chip opportunity-cost calculations use the chip prediction frames when a
  chip branch is evaluated.
- No-chip branches continue to use the ordinary transfer prediction frames.
- The benchmark now trains and caches a separate chip model only for chip
  modes, while preserving the existing no-chip path.
- Per-gameweek rows now record `chip_model_name` alongside the transfer and
  captain model metadata.
- The default portfolio remains Ridge/Ridge/Ridge, so the existing control
  path is unchanged by the new interface.
- Current and future total-points frames now share one fitted point-in-time
  model context, avoiding duplicate model fitting during historical runs.

## Validation

- Focused beam and portfolio tests: `6 passed` after the R2.2 additions.
- Full test suite: `156 passed`.
- Ruff: clean.
- `git diff --check`: clean apart from normal Windows line-ending warnings.
- Synthetic separation test confirmed that changing chip projections changes
  the Bench Boost counterfactual while the no-chip transfer counterfactual
  still selects the transfer-model upgrade.
- The mixed challenger used Ridge for transfers and captaincy and Gradient
  Boosting for chips, with the persisted M8.6.1 Ridge beam as champion:

| Season | Champion realistic | Challenger realistic | Delta | Champion hindsight | Challenger hindsight |
|---|---:|---:|---:|---:|---:|
| 2023/24 | 2,337 | 2,298 | -39 | 2,611 | 2,535 |
| 2024/25 | 2,489 | 2,526 | +37 | 2,709 | 2,744 |
| 2025/26 | 2,192 | 2,265 | +73 | 2,378 | 2,480 |

- Decision audit summary: captain regret changed by -37, -2, and +29 points;
  transfer decisions changed in 32, 30, and 24 Gameweeks; chip decisions
  changed in 3, 4, and 5 Gameweeks respectively.
- The Champion/Challenger gate passed: two seasons improved and the 2023/24
  regression remained below both configured seasonal guardrails.

## Runtime boundary

A first mixed-model run exceeded ten minutes before the shared model-context
cache was added. After the cache fix, the complete three-season challenger
run and decision audit completed successfully. Historical beam evaluation is
still expensive, so the cache is now part of the required validation path.

## Promotion decision

R2 passes its Champion/Challenger acceptance gate. The validated configuration
is Ridge transfer + Ridge captain + Gradient chip. It is a challenger result,
not a claim of guaranteed top-1% performance; production rollout should be
reviewed separately and the Ridge control remains available as fallback.

## Non-goals

- No changes to chip rules or historical chip inventories.
- No changes to the minutes model.
- No automatic transfer or chip execution.
- No rank-mode changes.
- No claim of top-1% performance.
