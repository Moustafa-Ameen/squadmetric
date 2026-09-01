# SquadMetric operations

SquadMetric is operated manually. The local Windows refresh task is intentionally
disabled; no scheduled refresh should be assumed.

## Install dependencies

Dependencies and build output are regenerable and are not part of the maintained
working tree.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

cd frontend
npm.cmd ci
cd ..
```

## Manual current-season refresh

Run this when fresh official data, post-Gameweek ingestion, recalibration, or new
manager-specific evidence is wanted:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1 `
  -TeamId YOUR_PUBLIC_FPL_TEAM_ID
```

The workflow refreshes official data, appends a newly finalized Gameweek at most
once, retrains the fixed serving family when required, rebuilds P10/P11/P12 reports,
settles eligible frozen evidence, and captures the next deadline decision. It never
performs an FPL action.

Safe read-only finalization check:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.post_gameweek_refresh `
  --season 2026-27 --dry-run
```

## Deadline evidence

```powershell
# Capture before the deadline
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence capture `
  --team-id YOUR_PUBLIC_FPL_TEAM_ID

# Inspect coverage
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence status

# Settle only after official finished + data_checked
.\.venv\Scripts\python.exe -m fpl_intelligence.live_decision_evidence settle `
  --season 2026-27 --gameweek GAMEWEEK
```

## Run locally

```powershell
# Terminal 1
.\.venv\Scripts\uvicorn.exe api.main:app --reload

# Terminal 2
cd frontend
npm.cmd run dev
```

Open <http://localhost:3000>. Check `GET /api/health` for liveness and
`GET /api/readiness` for decision-serving readiness.

## Retained local artifacts

The ignored `data/processed`, `data/raw`, and `models` trees contain the current
serving bundle, historical training data, immutable official snapshots, rules,
and deadline evidence. Compact accepted calibration and model-evaluation values
live under `data/reference` so old tournament runs and regenerable reports do not
need to remain in the working copy.

Production deployment requirements live in
[`frontend/DEPLOYMENT.md`](../frontend/DEPLOYMENT.md).
