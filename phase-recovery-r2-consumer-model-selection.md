# Recovery R2.1 — Consumer-Specific Model Selection

## Status

R2.1 and R2.2 are implemented and verified as experimental consumer-specific
model-selection infrastructure. Production routing remains unchanged:
M8.6.1 with the Ridge champion remains the reference system.

## Delivered

- Added `ProjectionPortfolio` with explicit transfer, captain, and chip model
  assignments.
- Fixed a hidden benchmark bug where realistic captain predictions silently
  used Ridge even when another `model_name` was requested.
- Added an independent captain-model override to the season benchmark.
- Added cache-key and persisted-row metadata for the captain model name.
- Added a separate chip projection path through the beam planner and benchmark.
- Added per-gameweek chip-model metadata for challenger runs.

## Corrected no-chip experiment

Gradient Boosting was evaluated for both transfer/lineup and captaincy while
the Ridge/M8.6.1 control remained unchanged:

| Season | Ridge realistic | Gradient transfer + captain | Change |
|---|---:|---:|---:|
| 2023/24 | 2,119 | 2,239 | +120 |
| 2024/25 | 1,903 | 2,129 | +226 |
| 2025/26 | 1,944 | 1,941 | -3 |

This is a promising no-chip challenger, but it is not a production result.
The earlier Gradient figures were partly mislabeled because captaincy had been
silently fitted with Ridge; these corrected figures use the requested model.

## Deliberate limitation

The separate path is now available, but no chip challenger has been promoted.
Ordinary transfer candidates remain transfer-model decisions; the chip model
is used for chip-branch squad construction and chip valuation. This is an
experimental separation, not evidence that the chip model is better.

A first mixed-model historical beam run exceeded its bounded runtime. After
shared point-in-time model-context caching was added, the three-season
chip-aware challenger run completed and passed the Champion/Challenger gate.
The validated experimental assignment is Ridge transfer + Ridge captain +
Gradient chip. It remains a challenger configuration with Ridge fallback,
not a guaranteed top-1% claim.

## Verification

- Focused R2.1/decision-audit tests: `9 passed` before R2.2 additions.
- R2.2 beam/portfolio tests: `6 passed`.
- Full pytest after R2.2: `156 passed` before the model-context cache change;
  the focused post-cache benchmark suite passed `29` tests.
- Ruff: clean.
- Existing benchmark controls unchanged.
