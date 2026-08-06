# FPL Intelligence

Recommendation-first Fantasy Premier League analytics for the live 2026/27
season. The application never executes transfers or chips automatically.

## Setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd frontend
npm.cmd install
cd ..
```

## Current-season refresh

The API fails closed when bootstrap, player, rules, fixture, and model artifacts
do not agree on the active season. Refresh the complete serving bundle from the
official FPL API before starting the application:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.refresh_current_season --season 2026-27
```

This preserves immutable bootstrap/fixture snapshots, rebuilds current player
tables, refits live-serving models using completed seasons only, writes the
rules and artifact manifests, and performs a real model-load readiness check.

For a normal daily refresh that reuses the reviewed serving-model bundle:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1
```

To register that refresh with Windows Task Scheduler, explicitly run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-daily-refresh.ps1
```

The refresh stops before model training if the decision-relevant rules contract
changes. Review the official change and use `--accept-rule-change` only after
the code and tests have been updated.

## Simulate previous seasons

Run the complete production portfolio—including realistic captaincy, transfers,
hits, historical chips, and season-specific rules—across every completed
season:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.simulate_seasons --preset production --seasons 2023-24 2024-25 2025-26
```

This is an expensive simulation. On the current development machine, a complete
chip-aware season takes roughly 15–20 minutes, so all three seasons can take
close to an hour. It prints each realistic season score and writes an isolated
manifest, season summary, and Gameweek decision file under
`data/processed/simulations/`. It never modifies the permanent benchmark-history
ledger. To run only the latest completed season, append
`--seasons 2025-26`.

Useful diagnostic presets:

```powershell
# Ridge-only rollback portfolio, with chips
.\.venv\Scripts\python.exe -m fpl_intelligence.simulate_seasons --preset control

# Current transfer/captain models, without chips
.\.venv\Scripts\python.exe -m fpl_intelligence.simulate_seasons --preset no-chip

# Static-squad diagnostic
.\.venv\Scripts\python.exe -m fpl_intelligence.simulate_seasons --preset diagnostic-no-transfers
```

Run the checkpointed consumer-specific model tournament (P4):

```powershell
# Fast, non-promotional screen
.\.venv\Scripts\python.exe -m fpl_intelligence.consumer_model_tournament --stage screening --seasons 2024-25

# Complete chip-aware finalist replay; use --resume after interruption
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

P4 writes isolated checkpoints and acceptance artifacts. It does not modify the
production model portfolio automatically.

Audit any completed simulation for exact score reconciliation, explicitly
labelled decision-regret diagnostics, chip counterfactuals, and source-backed
historical top-1% bounds:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.points_loss_audit --simulation-dir data/processed/simulations/<run-directory>
```

Audit the accepted post-recovery production scorecard across 2023/24, 2024/25,
and 2025/26:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.points_loss_audit --recovery-scorecard
```

This writes a canonical 114-Gameweek audit under
`data/processed/points_loss_audits/post-recovery-production-v1`, including
decision-opportunity and selected-chip-health artifacts.

The audit writes separate P2 artifacts into the simulation directory. Hindsight
regret buckets overlap and are diagnostic upper bounds; they are never added to
the simulated score. Older simulations that did not persist the active squad,
ordered bench, or transfer player IDs remain auditable for score and captaincy,
while unsupported loss buckets are reported as `unavailable`.

## Initial-squad championship

Run the point-in-time-safe P3 opening-squad tournament:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.initial_squad_championship
```

The command checkpoints every completed season-policy path and safely resumes
the same output directory after interruption. It is expensive because each
distinct opening squad receives a complete chip-aware 38-Gameweek continuation.

The corrected championship promoted
`horizon_8_flexible_cold_start_safe`. Against the identity-safe control it
scores 0, +198, and +12 realistic points across the three supported seasons,
for +210 aggregate points with no seasonal regression. The production
simulation preset and live initial-squad endpoint now use this policy; the
control preset remains the explicit rollback. Full evidence is recorded in
`phase-performance-recovery-initial-squad.md`.

## Backend

```powershell
.\.venv\Scripts\uvicorn.exe api.main:app --reload
```

- Liveness: `GET /api/health`
- Artifact/model readiness: `GET /api/readiness`
- Live season status: `GET /api/fpl/season-state`

Copy `.env.example` values into your local environment when hosts or ports
differ.

## Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` for non-default API
deployments.

## Quality gates

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check api tests src
cd frontend
npm.cmd run test:search
npm.cmd run lint
npm.cmd run build
```
