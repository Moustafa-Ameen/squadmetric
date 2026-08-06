# P4 — Consumer-Specific Model Tournament

## Status

Completed on 2026-08-06/07. The tournament infrastructure, screening run,
complete three-season finalist run, checkpoint validation, and acceptance audit
are finished. No production model routing was changed automatically.

## Purpose

Earlier experiments often changed the same projection model for transfers,
captaincy, lineup selection, and chips at once. That made a higher season score
impossible to attribute to one consumer and allowed aggregate gains to conceal
large seasonal losses.

P4 evaluates one declared consumer assignment at a time. Model quality is judged
by realistic downstream decisions in the complete simulator, not by prediction
MAE alone.

## Delivered

- Added a distinct `lineup_model` to `ProjectionPortfolio` and persisted
  `lineup_model_name` in benchmark rows.
- Routed starting-XI and bench selection through the lineup model without
  changing transfer, captain, or chip projections.
- Added a deterministic, checkpointed P4 runner with screening and full stages.
- Added hash-validated checkpoint resume, champion-artifact import, run
  manifests, per-Gameweek comparisons, regime summaries, and acceptance rows.
- Fixed the production opening squad for every model consumer candidate. Only
  the explicit initial-squad control may change it.
- Added a bounded shared prediction cache. It retains predictions but no longer
  stores a complete expanding historical training table for every Gameweek;
  point-in-time training history is reconstructed on cache hits.
- Kept production routing immutable during the tournament.

## Candidate funnel

The 2024/25 no-chip screening stage was non-promotional. It removed candidates
that were clearly unsuitable for the expensive full replay:

- Gradient captain: -19 realistic points and worse captain regret.
- Conditional minutes: -15 points.
- Availability/role minutes: -62 points.
- Component projection: -102 points.
- Team-component projection: -171 points.

The promoted P3 opening-squad policy was retained as the common full-stage
opening squad rather than retested as a model consumer. Chip models require the
chip-aware stage and could not be judged in screening.

Full-stage finalists were Gradient transfer, Ridge chip, Gradient lineup, and
the horizon-value hit policy.

## Complete chip-aware result

The production champion reconciled exactly to the accepted scorecard:

| Season | Champion realistic | Champion hindsight | Chips |
|---|---:|---:|---:|
| 2023/24 | 2,321 | 2,575 | 5 |
| 2024/25 | 2,360 | 2,600 | 5 |
| 2025/26 | 2,249 | 2,515 | 8 |

Finalist realistic scores and deltas:

| Candidate | 2023/24 | Delta | 2024/25 | Delta | 2025/26 | Delta | Aggregate delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ridge chip model | 2,332 | +11 | 2,486 | +126 | 2,211 | -38 | +99 |
| Gradient transfer model | 2,208 | -113 | 2,536 | +176 | 2,093 | -156 | -93 |
| Gradient lineup model | 2,320 | -1 | 2,372 | +12 | 2,223 | -26 | -15 |
| Horizon-value hit policy | 2,218 | -103 | 2,138 | -222 | 2,208 | -41 | -366 |

## Acceptance decisions

### Ridge chip model — validated challenger, not production-promoted

Ridge improves two seasons, adds 99 aggregate realistic points, changes chip
decisions, and keeps its worst seasonal loss inside the predefined guardrail.
It therefore passes the P4 consumer gate.

The result has an important current-season caveat: it loses 38 points in the
latest eight-chip validation season and loses points in every historical
blank/double regime grouping. Its aggregate gains come from normal Gameweeks,
especially 2024/25. Because 2026/27 also uses eight chips, P4 does not
automatically replace the active Gradient chip model. That requires a deliberate
integrated review and later live shadow evidence.

### Gradient transfer model — rejected

The model improves 2024/25 by 176 points but loses 113 and 156 in the other two
seasons. Two severe seasonal regressions and only one improving season make the
older aggregate/coupled Gradient result unsuitable for production.

### Gradient lineup model — rejected

The lineup assignment changes starting XIs and improves 2024/25 by 12 points,
but loses 1 and 26 in the other seasons. It improves only one validation season
and has a negative aggregate result.

### Horizon-value hit policy — rejected and confounded

The candidate selects zero hits in all three seasons and fails every performance
season. It also changes the beam's maximum transfer branches from six to two,
which changes transfers, squads, captaincy, and chips even when no -4 is taken.
Its score is therefore not a clean estimate of hit value. The current policy is
not promoted; P7 must isolate hit valuation from beam breadth before retesting.

## Evidence integrity

- 570 persisted decision rows: five tracks, three seasons, 38 Gameweeks.
- Zero duplicate candidate/season/Gameweek keys.
- Every group contains all 38 Gameweeks.
- All 15 checkpoint decision files match their metadata SHA-256 hashes.
- All five final artifacts match the run-manifest SHA-256 hashes.
- Zero model-training cutoff violations.
- Zero captain-training cutoff violations.
- Rules versions and data cutoffs are present on every decision row.
- The screening stage is explicitly non-promotional.
- Production portfolio files were not modified by tournament acceptance.

Engineering verification after the final audit:

- Focused P4 and historical benchmark suite: 29 passed.
- Complete repository suite: 211 passed.
- Repository-wide Ruff: clean.
- `git diff --check`: clean apart from normal Windows line-ending notices.

Artifacts are under
`data/processed/consumer_tournaments/p4-full-finalists/`. The representative
screen is under
`data/processed/consumer_tournaments/p4-screening-2024-25/`.

## Reproduce

Screen candidates cheaply without chips:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.consumer_model_tournament `
  --stage screening `
  --seasons 2024-25 `
  --output-dir data/processed/consumer_tournaments/p4-screening-local
```

Run or resume the complete finalists using the accepted champion artifacts:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.consumer_model_tournament `
  --stage full `
  --seasons 2023-24 2024-25 2025-26 `
  --candidates transfer_gradient chip_ridge lineup_gradient hit_horizon_value `
  --output-dir data/processed/consumer_tournaments/p4-full-finalists `
  --champion-artifacts `
    data/processed/simulations/chip-save-value-repair-2023-24 `
    data/processed/simulations/chip-save-value-repair-2024-2026 `
  --resume
```

## Phase boundary

P4 is complete. P5 has not started. The production portfolio remains unchanged
pending an explicit promotion decision; rejected P4 candidates must not be
stacked into production.
