# SquadMetric operations

SquadMetric does not use an unattended Windows refresh task. The local launcher
checks for finalized FPL data and transactionally refreshes the prediction bundle
before starting the website. This updates application data only and never performs
an FPL action. Pass `-SkipDataRefresh` to `start.cmd` or `start.ps1` only when the
last validated bundle should be used unchanged.

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
  -TeamId YOUR_PUBLIC_FPL_TEAM_ID `
  -ModelTeamId SQUADMETRIC_MODEL_TEAM_ID
```

The workflow refreshes official data, appends a newly finalized Gameweek at most
once, retrains the fixed serving family when required, settles eligible frozen
evidence, and captures the next deadline decision. Preseason opening-squad
robustness and finalization artifacts are immutable once GW1 begins; only the
current set-piece audit is rebuilt in season. It never performs an FPL action.

`-TeamId` is a personal diagnostic account and is never counted as product
performance. `-ModelTeamId` must identify the actual FPL account created for the
SquadMetric squad; it writes a separate official per-Gameweek scorecard and freezes
that account's next recommendation evidence.

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

The live planner reconstructs bank, purchase/selling prices, and free transfers
from public FPL entry, pick, transfer, chip, and history payloads. The Gameweek
Plan labels that provenance and lets the manager correct bank or free transfers;
the confirmed values are stored per Team ID and used consistently by the dashboard
and planner. Passwords and authenticated FPL sessions are never requested.

Transfer recommendations use a rolling three-, five-, or eight-Gameweek search.
The search evaluates linked same-deadline packages, net points after hits, a
time-decayed future, the option value of a saved free transfer, bank remaining,
and priority replacement of confirmed non-players. A package may therefore include
a downgrade that releases cash for a second upgrade. Future steps are planning
directions only and are recalculated at every deadline. Personalized chip calls
remain disabled; the Chip Guide reports general fixture opportunities instead.

The primary outcome metric is realized net points versus the frozen legal
no-action branch. Supporting checks are transfer and captain regret, top-player
ranking quality, minutes/availability calibration, legality and state mismatch
rates, recommendation churn, stale-state abstentions, runtime, and candidate-set
coverage. Deadline evidence must freeze the generated root set before the deadline
and settle only from finalized official results.

## Run locally

Normal launch checks for new finalized gameweeks before opening the site:

```powershell
.\start.cmd
```

The refresh is idempotent, keeps the last validated bundle if publishing fails,
and never makes transfers or uses chips. For diagnostics that must not update the
bundle, use `start.cmd -SkipDataRefresh`.

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
