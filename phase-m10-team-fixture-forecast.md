# Phase M10 — Team, Fixture, and Calibrated Component Forecasting

## Status

M10 implementation is complete for this phase, but the acceptance gate failed.
It remains an opt-in experimental candidate and does not replace the accepted
M8.6.1 chip-aware control, M3 xG/xA control, or the provisional M9 availability
model.

## Implemented slice

- `team_forecast.py` provides a deterministic, shrunk Poisson-style team-goal
  model.
- Processed player rows are converted into fixture rows and duplicate player
  perspectives are collapsed before fitting.
- Fits are strictly point-in-time safe: only gameweeks earlier than the
  requested cutoff are used.
- Forecasts include expected home and away goals, result probabilities, clean
  sheet probabilities, fixture status, rules version, data cutoff, training
  match count, and model version.
- `calibration.py` provides binary Brier/log-loss diagnostics, reliability
  tables, Poisson MAE/RMSE/log-loss, central interval coverage, and an
  optional sparse-safe isotonic calibrator.
- Component projection models can be filtered by both BPS and DC rule regime;
  selected training regimes are retained in model metadata.
- `projection_distributions.py` now supports a held-out residual calibrator that
  records the calibration cutoff separately from the future forecast cutoff.
- `player_component_forecast.py` provides an opt-in bridge from fixture team
  goals/clean-sheet probabilities to player goals, assists, clean sheets,
  conceded goals, goalkeeper-save proxy, and DC components. It consumes only
  lagged player xG/xA signals and suppresses DC under `pre_dc`.
- A walk-forward evaluator produces season-level out-of-sample diagnostics.

## Focused validation

The new M10 tests pass, as do the relevant historical, fixture, rules, and
component regression tests. The existing accepted benchmark control was not
changed.

Walk-forward team-layer diagnostics on the current processed historical table:

| Season | Fixtures | Home goal MAE | Away goal MAE | Clean-sheet Brier | 80% interval coverage (home/away) |
|---|---:|---:|---:|---:|---:|
| 2023/24 | 390 | 1.123 | 1.001 | 0.156 | 89.7% / 91.3% |
| 2024/25 | 385 | 1.039 | 0.907 | 0.176 | 92.2% / 94.0% |
| 2025/26 | 385 | 0.993 | 0.875 | 0.187 | 93.8% / 92.5% |

These are model-quality diagnostics only. They are not FPL points totals and
do not establish that the team layer improves transfers, captaincy, or chips.
The fixture counts also need reconciliation against the canonical historical
fixture source before being used as a final acceptance artifact.

The temporary processed-table rebuild reconciled exactly at the persisted-file
level: 85,311 rows, identical per-season row counts, and an identical SHA-256
hash to the existing processed table. A direct pandas frame comparison was not
used as the acceptance criterion because CSV reloads can differ in in-memory
dtype/NA representation even when persisted bytes are identical.

Regression status after the shared component API change:

- Focused M10/component tests: pass.
- Full pytest: 145 passed.
- Full Ruff: clean.
- Accepted M8.6.1 control path: unchanged; M10 remains opt-in.

## Decision-metric evaluation

The M10 projection mode was evaluated without changing the accepted control.
The first no-transfer comparison was not apples-to-apples: it compared M10's
no-transfers strategy with the deterministic-transfer control. The matched
2024/25 no-transfers comparison is:

| Track | Realistic | Hindsight |
|---|---:|---:|
| Existing no-transfers control | 1,044 | 1,189 |
| M10 team components | 962 | 1,189 |

The 82-point loss is therefore a realistic-captaincy regression; hindsight
starting-XI points were unchanged. Matched deterministic-transfer/no-chip
results are:

| Season | Existing Ridge realistic | M10 realistic | M10 change | M10 hindsight change |
|---|---:|---:|---:|---:|
| 2023/24 | 2,119 | 1,896 | -223 | -54 |
| 2024/25 | 1,903 | 1,897 | -6 | +153 |
| 2025/26 | 1,944 | 1,601 | -343 | -339 |

M10 therefore remains a severe transfer/lineup regression in 2025/26 and a
captaincy-conversion regression in the earlier seasons.

The 2024/25 deterministic-transfer baseline-planner chip diagnostic produced:

| Track | Realistic | Hindsight | Chips | Hits |
|---|---:|---:|---:|---:|
| M10 team components, baseline planner | 2,085 | 2,484 | 5 | 0 |
| Accepted M8.6.1 beam control | 2,489 | 2,709 | 5 | 0 |

These are different chip planners and are not a valid direct acceptance
comparison. The complete M10 team-component beam track did not finish within
the runtime gate, so no complete M10 chip-aware score is claimed.

The primary M10 beam track exceeded the 20-minute runtime gate twice before
producing a complete season result. The M10 mode was optimized to reuse the
point-in-time minutes/team context across future horizons, but it remains too
slow for the full beam acceptance run and fails the matched no-chip diagnostics.

### M10 acceptance decision: failed / provisional

M10 is not production-ready and is not stacked into the accepted system. The
team-context bridge needs targeted component diagnostics and a new calibrated
player-event model before another benchmark attempt. The goalkeeper-save proxy
must also be replaced or independently validated. No aggregate improvement is
claimed, and the accepted M8.6.1 control remains the reference.

## Remaining M10 work

- Add standalone calibration curves and interval-coverage validation for the
  new player component bridge.
- Replace the goalkeeper-save proxy with a validated shot/save model.
- Add set-piece/penalty-role and position-aware bonus models.
- Evaluate transfer, captaincy, and chip decision metrics walk-forward by
  season, with no aggregate masking.
- Rework the failed bridge and rerun the complete decision-metric acceptance
  review before any production promotion.

M10 remains failed/provisional until the severe regression and runtime gate are
resolved and a complete chip-aware multi-season evaluation passes.
