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
tables, writes the rules and artifact manifests, and performs a real model-load
readiness check. Before the season, models use completed historical seasons.
After the season starts, a direct full refresh also retains all officially
finalized 2026/27 Gameweeks already present in the live training table.
It also writes timestamped availability events and applies reviewed launch
evidence for promoted/new players. Official injury status always caps any role
prior, and every evidence file is hash-tracked by the serving manifest.

The production opening-squad endpoint is:

```text
GET /api/predictions/initial-squad?horizon=8
```

Its response includes the active production policy/version, budget and bank,
availability probability, starting likelihood, and source metadata for any
launch evidence used in the selected squad.

For the normal daily and post-Gameweek refresh:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1
```

The command always refreshes official bootstrap, fixtures, prices, availability,
rules, and serving manifests. It retrains the fixed serving-model family only
when FPL marks a new Gameweek both `finished` and `data_checked`. The new rows
come from the latest immutable bootstrap snapshot captured before that
Gameweek's deadline; provisional outcomes and post-deadline prices/ownership are
rejected. If no Gameweek is newly finalized, the model bundle is unchanged.

Before GW1, the command also captures an immutable opening recommendation under
`data/processed/gw1_shadow/`. Inspect freshness, the latest decision hash, and
the deadline checklist at `GET /api/operations/deadline-readiness`. A manual
capture can be run with:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_gw1_shadow
```

The daily refresh rebuilds the P10 robustness tournament and P11 deadline gate
before it captures deadline evidence. This deliberately takes several minutes:
a snapshot is never written against a stale robustness hash.

To validate a newly finalized Gameweek without publishing any history, model,
snapshot, outcome, or run-report file:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.post_gameweek_refresh --season 2026-27 --dry-run
```

Published current-season rows are stored separately in
`data/processed/live_2026_27_player_gw.csv`. Official event-live payloads,
cutoffs, and hashes are immutable. Model/history publication and frozen-outcome
settlement are one rollback-protected operation. A failed readiness check
restores the prior serving bundle.

### Live decision evidence

Before every deadline, freeze the production recommendation and its complete
generated transfer/chip branch set. Before GW1, `--team-id` is optional; after
GW1 it is required so the current squad, bank, free transfers, and chip state
can be captured.

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence capture --team-id YOUR_TEAM_ID
```

The command records data/rules hashes, deadline-safe news, every legal root
branch considered, the selected branch, squad/XI/bench/captain state, hits,
chips, bank, and uncertainty under `data/processed/live_decision_evidence/`.
It never executes a transfer or chip. Check coverage with:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence status
```

After FPL marks a Gameweek both finished and data-checked, settle the frozen
branches against official points:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence settle --season 2026-27 --gameweek 1
```

Settlement is fail-closed while scoring remains provisional. It applies the
frozen bench order, legal autosubs, captain/vice fallback, Bench Boost, Triple
Captain, and transfer hits, then records selected-branch regret against the
same candidate set that existed before the deadline. Operational status is
also available at `GET /api/operations/shadow-evidence`.

Run the P10 opening-squad calibration and robustness tournament after a
material projection, scoring-rule, or player-pool change:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.p10_calibration
```

This calibrates bench-cover value from accepted historical decision rows and
tests the live squad across 27 autosub, BPS, and team-role scenarios. The
initial-squad API exposes each selected player's `locked`, `stable`, or
`fragile` classification only when the report's bootstrap hash matches the
current serving artifacts. To refresh only the historical autosub portion of
an existing report, use `--calibration-only`.

Run the P11 deadline report directly with:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.p11_deadline_finalization
```

The recommendation remains in `monitoring` until it is inside the final
24-hour window and official final team news has been reviewed. The final manual
refresh must cite at least one official source:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1 `
  -FinalNewsReviewed `
  -FinalNewsSource "https://www.premierleague.com/..."
```

This acknowledgment is fail-closed: `-FinalNewsReviewed` without an official
source URL is rejected.

Run the P12 official penalty and set-piece role audit directly with:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.p12_set_piece_report
```

P12 preserves official penalty, direct-free-kick, and corner role fields and
applies only the change from each player's final 2025/26 role. This prevents an
established taker's historical penalty returns from being counted a second
time. The initial-squad API and planner show the normalized current roles, and
the full audit is written to `data/processed/p12_set_piece_report.json`.

To register that refresh with Windows Task Scheduler, explicitly run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-daily-refresh.ps1
```

After GW1, register your FPL team ID so the scheduled task can freeze planner
evidence as well as refresh public data:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-daily-refresh.ps1 -TeamId YOUR_TEAM_ID
```

Without a team ID, finalized-data ingestion and serving refresh still run, but
post-GW1 decision-evidence capture is explicitly skipped with a warning.

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
