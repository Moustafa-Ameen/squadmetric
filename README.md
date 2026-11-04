<p align="center">
  <img src="docs/assets/squadmetric-banner.svg" width="100%" alt="SquadMetric — Smarter FPL Decisions" />
</p>

<h1 align="center">SquadMetric</h1>

<p align="center">
  <strong>Recommendation-first Fantasy Premier League intelligence for the live 2026/27 season.</strong>
</p>

<p align="center">
  One primary recommendation, ranked alternatives, and the evidence needed to make the final call.
</p>

<p align="center">
  <a href="https://squadmetric.vercel.app"><strong>Live site</strong></a> ·
  <a href="https://squadmetric.vercel.app/proof"><strong>Performance evidence</strong></a>
</p>

<p align="center">
  <a href="https://github.com/Moustafa-Ameen/squadmetric/actions/workflows/quality.yml"><img alt="Quality checks" src="https://github.com/Moustafa-Ameen/squadmetric/actions/workflows/quality.yml/badge.svg" /></a>
  <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" />
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-live-009688?logo=fastapi&logoColor=white" />
  <img alt="Backend tests" src="https://img.shields.io/badge/pytest-365%20passing-22c55e" />
  <img alt="Browser tests" src="https://img.shields.io/badge/browser%20tests-53%20passing-8b5cf6" />
</p>

<p align="center">
  <a href="#why-squadmetric">Why SquadMetric</a> ·
  <a href="#results">Results</a> ·
  <a href="#features">Features</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#historical-simulation">Simulation</a> ·
  <a href="#quality-and-safety">Quality</a>
</p>

> [!IMPORTANT]
> SquadMetric is **top-1%-oriented**, not a top-1% guarantee. It recommends transfers, captaincy, bench order, and chips, but it never logs into FPL or executes an action automatically.

## Why SquadMetric

Most FPL tools begin with tables. SquadMetric begins with the decision.

| The question | What SquadMetric returns |
|---|---|
| Who should I captain? | A primary captain, vice-captain, start probability, expected points, and alternatives |
| Should I transfer now? | Full-squad impact, hit cost, bank/free-transfer state, and the value of waiting |
| When should I use a chip? | Rule-legal chip branches, immediate gain, horizon gain, and future opportunity cost |
| Who starts and who is benched? | A legal XI, formation, ordered autosub bench, and Bench Boost-aware valuation |
| Can I trust the recommendation? | Rules/data hashes, point-in-time cutoffs, uncertainty, persisted evidence, and historical tests |

The default objective is simple:

```text
maximize realistic expected FPL points
- transfer hits
- downside and uncertainty
- future opportunity cost
+ squad flexibility
```

The plan maximizes points. There is no rank-chasing mode.

## Results

These are simulated replays of three completed seasons, not real FPL teams. They use the planner settings behind the live site, with only the data available before each deadline. Scores are after transfer hits.

| Season | SquadMetric | Same planner, no chips | Official average manager | Above average | Top 1% cutoff |
|---|---:|---:|---:|---:|---:|
| 2023/24 | 2,146 | 2,142 | 2,003 | +143 | Not available |
| 2024/25 | 2,353 | 2,275 | 2,008 | +345 | About 2,504–2,508 |
| 2025/26 | 2,369 | 2,051 | 1,895 | +474 | About 2,296–2,319 |

What these numbers do and do not show:

- **Against the average manager:** the planner finished ahead in all three seasons, but the average includes casual and inactive teams.
- **Against the top 1%:** 2025/26 clears the cutoff, but that season helped set the chip rules. 2024/25 falls short, and no cutoff was found for 2023/24.
- **Against no chips:** the SquadMetric column adds timed chips and captain and double-Gameweek changes. It finished 4, 78, and 318 points ahead. Only the 2025/26 gain is clear of chance; 2023/24, the season held back to check the chip rules, is effectively a tie.
- **Reliability:** these seasons helped choose the model, so the results may be flattering. Small input changes moved single seasons by more than 100 points, so treat each figure as approximate.
- **Live results:** none of this is proven on real Gameweeks yet. The simulations also lack live injury news and set-piece updates.

An audit found that earlier replays had used end-of-season opponent ratings, which reveal how each team's season turned out. These results rebuild those ratings from earlier results only, and they replace higher and lower figures published before. See [docs/decision-history.md](docs/decision-history.md).

## Features

### Decision engine

- Multi-Gameweek player projections with appearance and availability adjustment.
- Deterministic 15-player squad, XI, bench-order, captain, and vice-captain selection.
- Transfer planning with free-transfer banking, sale price, bank, and optional `-4` hits.
- Chip-aware state for Wildcard, Free Hit, Bench Boost, and Triple Captain.
- Blank and Double Gameweek fixture scenarios that decide when fixture-driven chips are worth playing.
- Ranked alternative plans each week, plus maximum-points, balanced, and safer-depth opening-squad profiles.
- Penalty, direct-free-kick, and corner-role transition intelligence.

### Live 2026/27 intelligence

- Official FPL player IDs, teams, positions, prices, ownership, status, and availability.
- Instant onboarding for newly added players without blocking the website.
- Live fixture changes and postponements applied when a page refreshes.
- Rule-versioned eight-chip inventory with the GW19 half-season reset.
- Separate 2026/27 BPS and defensive-contribution regimes.
- Next-deadline targeting even while the current Gameweek is in progress.
- Projection caching that reacts to actionable changes but ignores live score/BPS noise.

### Product experience

- Recommendation-first dashboard.
- Visual pitch for the current squad and recommended XI.
- Weekly transfer, captaincy, bench, chip, player, and fixture pages.
- Guest-first onboarding with a full demo workspace, public FPL Team ID, or official URL.
- Browser-local team link, preferences, drafts, watchlist, and decision history.
- Responsive desktop/mobile interface with graceful live-data fallbacks.

### Evidence and operations

- Immutable official-data snapshots and SHA-256 hashes.
- Rules, model, fixture, and data-cutoff contracts.
- Historical simulation across multiple rule eras, using only pre-deadline data in published results.
- Persisted pre-deadline decisions and post-Gameweek settlement.
- No-chip controls, counterfactual branches, and acceptance gates.
- Automated Python, TypeScript, lint, build, accessibility, desktop, and mobile checks.

## How it works

```mermaid
flowchart LR
    A[Official FPL API] --> B[Rules & data contracts]
    B --> C[Immutable snapshots]
    C --> D[Availability & role intelligence]
    D --> E[Multi-GW projections]
    E --> F[Squad / transfer / chip planner]
    F --> G[Primary recommendation]
    F --> H[Ranked alternatives]
    G --> J[Dashboard & decision evidence]
    H --> J
    J --> K[Post-GW settlement]
    K --> E
```

The system improves during the season through a guarded feedback loop:

1. Official prices, status, roles, and fixtures are read live.
2. Finalized Gameweeks are ingested only after FPL marks them finished and data-checked.
3. New training rows preserve the original pre-deadline market snapshot.
4. New models and decision policies are tested against fixed controls.
5. A candidate is promoted only when decision metrics pass—not because MAE looks better.

## Architecture

```mermaid
graph TD
    UI[Next.js 16 frontend] --> API[FastAPI service]
    UI --> LOCAL[Browser-local manager state]
    API --> LIVE[Official FPL API]
    API --> ART[Validated serving artifacts]
    ART --> MODELS[scikit-learn models]
    ART --> RULES[Season rules manifests]
    ART --> DATA[Historical + live datasets]
    API --> OPT[Deterministic planners]
    OPT --> AUDIT[Decision evidence & simulations]
```

| Layer | Technology | Responsibility |
|---|---|---|
| Web | Next.js 16, React 19, TypeScript, Tailwind CSS | Guest onboarding, dashboard, team, planner, players, fixtures, proof |
| API | FastAPI, Pydantic, httpx | Live FPL access, readiness, projections, recommendations |
| Intelligence | pandas, NumPy, scikit-learn, SciPy | Features, projections, calibration, deterministic optimization |
| Local state | Browser `localStorage` | Team link, preferences, drafts, watchlist, decision history |
| Validation | pytest, Ruff, ESLint, Playwright, axe | Correctness, leakage protection, accessibility, responsive flows |

## Quick start

### Prerequisites

- Windows PowerShell (the maintained production/development path).
- Python 3.13.
- Node.js 24 and npm.

### 1. Install

```powershell
git clone https://github.com/Moustafa-Ameen/squadmetric.git
cd squadmetric

py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"

cd frontend
npm.cmd install
cd ..
```

### 2. Configure

The API defaults work locally. Copy values from `.env.example` only if you need to override hosts, ports, season, or readiness limits. The public launch is guest-first: no identity provider, OAuth app, database, or email service is required.

### 3. Run

From the repository root, one command starts the API and website, waits for both
to become ready, and opens [http://localhost:3000](http://localhost:3000):

```powershell
.\start.cmd
```

Keep that terminal open while using SquadMetric. Press `Ctrl+C` to stop both
services. Startup logs are written under `.runtime/squadmetric/`. On a fresh clone,
the launcher creates the Python environment and installs dependencies when needed.
A validated serving bundle is already committed, so it does not refresh season data
or create any schedule unless you add `-RefreshData`.

SquadMetric stores the linked Team ID, preferences, drafts, watchlist, and decision
history in the visitor's browser. It does not request an FPL password or create a
SquadMetric account.

The default launcher uses an optimized frontend build so page-to-page navigation
stays fast. It rebuilds only when frontend source files change. Use
`.\start.cmd -Dev` when actively editing the website and you need hot reload.

To start without opening a browser, use `.\start.cmd -NoBrowser`. Optional
`-BackendPort` and `-FrontendPort` arguments can override the default ports.
The wrapper bypasses local `.ps1` execution-policy restrictions only for this run;
it does not change the machine's PowerShell policy.

Useful health checks:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Process liveness |
| `GET /api/readiness` | Artifact and model contract |
| `GET /api/fpl/season-state` | Live season and recommendation readiness |
| `GET /api/predictions/overview` | Compact dashboard decision payload |
| `GET /api/predictions/initial-squad?horizon=8` | Opening-squad recommendation |
| `GET /api/operations/deadline-readiness` | Final deadline checklist |

## Data refresh and post-Gameweek operation

The `Data refresh` GitHub workflow runs on GitHub's servers at 07:30 and 16:30 UTC every day, so nothing needs to run on a personal computer. It publishes new serving data and retrained models only after a newly finalized, data-checked Gameweek passes the test suite. See [docs/operations.md](docs/operations.md).

To refresh locally instead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1
```

It refreshes official data every run and retrains only after a newly finalized, data-checked Gameweek is available. Provisional results and post-deadline market values are rejected.

To rebuild only the serving bundle from the latest official data:

```powershell
.\.venv\Scripts\python.exe -m squadmetric.refresh_current_season --season 2026-27
```

<details>
<summary><strong>Pre-deadline evidence capture</strong></summary>

Freeze the production recommendation and every generated transfer/chip branch before a deadline:

```powershell
.\.venv\Scripts\python.exe -m squadmetric.live_decision_evidence capture --team-id YOUR_TEAM_ID
.\.venv\Scripts\python.exe -m squadmetric.live_decision_evidence status
```

After FPL finalizes scoring, settle the frozen decisions:

```powershell
.\.venv\Scripts\python.exe -m squadmetric.live_decision_evidence settle --season 2026-27 --gameweek 1
```

Settlement applies legal autosubs, bench order, captain/vice fallback, Bench Boost, Triple Captain, and transfer hits. It never uses a branch created after the deadline.

</details>

<details>
<summary><strong>Final-news lock</strong></summary>

Inside the final 24-hour window, record the reviewed official source:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1 `
  -FinalNewsReviewed `
  -FinalNewsSource "https://www.premierleague.com/..."
```

The acknowledgment is fail-closed: `-FinalNewsReviewed` without an official source URL is rejected.

</details>

<details>
<summary><strong>Preseason robustness and set pieces</strong></summary>

```powershell
# Preseason-only autosub calibration and opening-squad robustness
.\.venv\Scripts\python.exe -m squadmetric.p10_calibration

# Preseason-only deadline finalization report
.\.venv\Scripts\python.exe -m squadmetric.p11_deadline_finalization

# Current official penalties, direct free kicks, and corners audit
.\.venv\Scripts\python.exe -m squadmetric.p12_set_piece_report
```

The refresh script preserves the first two outputs once GW1 has begun; it does not
rewrite opening-squad evidence with later information. Set-piece intelligence
applies only the change from the final 2025/26 role, preventing established penalty
returns from being counted twice.

</details>

## Historical simulation

Reproduce the [published results](#results), including realistic captaincy, transfers, hits, chips, and season-specific rules:

```powershell
# SquadMetric column
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons `
  --preset pit-timed-chips `
  --seasons 2023-24 2024-25 2025-26

# Same planner without chips
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons `
  --preset pit-no-chips `
  --seasons 2023-24 2024-25 2025-26
```

These need the local historical data in `data/processed/`, which is not committed. Each run writes isolated manifests, season summaries, and Gameweek decisions under `data/processed/simulations/`. The permanent benchmark ledger is never modified by this command.

> [!NOTE]
> Full replays are intentionally expensive. A season took roughly 20–25 minutes on the development machine.

Older single-transfer presets, kept for comparison. They use end-of-season opponent ratings, so their results are not comparable with the table above:

```powershell
# Earlier production portfolio
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons --preset production

# Ridge rollback portfolio with chips
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons --preset control

# Earlier transfer/captain models without chips
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons --preset no-chip

# Static-squad diagnostic
.\.venv\Scripts\python.exe -m squadmetric.simulate_seasons --preset diagnostic-no-transfers
```

Audit a completed simulation:

```powershell
.\.venv\Scripts\python.exe -m squadmetric.points_loss_audit `
  --simulation-dir data/processed/simulations/RUN_DIRECTORY
```

### Opening-squad championship

```powershell
.\.venv\Scripts\python.exe -m squadmetric.initial_squad_championship
```

The checkpointed tournament tests each opening squad through a complete chip-aware 38-Gameweek continuation. The accepted `horizon_8_flexible_cold_start_safe` policy scored 0, +198, and +12 points against its identity-safe control across 2023/24, 2024/25, and 2025/26, a +210 total with no season behind the control. That comparison came from an older simulator with end-of-season opponent ratings and has not been re-measured, so it is not comparable with the [results above](#results). See [docs/decision-history.md](docs/decision-history.md) for the evidence and rejected variants.

## Rules and data integrity

Every supported season has an explicit contract for:

- budget, squad size, formations, club limits, transfers, and price handling;
- scoring, BPS, and defensive-contribution regimes;
- chip inventory, legal windows, resets, and restrictions;
- source URL, retrieval/cutoff timestamps, schema version, and payload hash.

Non-negotiable safeguards:

- Published simulations use only information available before each deadline. Older simulator presets, and the accuracy, captain, and top-player tables on the evidence page, still use end-of-season opponent ratings; the live models also train on them, with a small measured effect on forecasts.
- Missing defensive-contribution data stays missing; it is never zero-filled.
- Scoring/BPS/DC regimes are never blended across rule changes.
- Free Hit reverts squad, bank, and transfer state; Wildcard changes are permanent.
- Bench points count only through autosubs or Bench Boost.
- Assistant Manager exists only in the historical 2024/25 rules regime.
- Model promotion requires realistic decision improvement, not MAE alone.
- A detected rules-contract change blocks affected recommendations until reviewed.

## Quality and safety

Run the complete local quality gates:

```powershell
# Backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

# Frontend
cd frontend
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run test:unit
npm.cmd run test:e2e
npm.cmd run build
```

Current verified baseline:

| Gate | Result |
|---|---:|
| Python tests | 365 passing (26 need local data, so GitHub runs 339) |
| Frontend unit tests | 40 passing |
| Desktop/mobile browser tests | 53 passing, 1 skipped |
| Ruff, ESLint, TypeScript | Clean |
| Next.js production build | Passing |

GitHub Actions runs the repository quality workflow on every push and pull request.

## Repository map

```text
squadmetric/
├── api/                      FastAPI application and live FPL routes
├── frontend/                 Next.js SquadMetric website
├── src/squadmetric/         Models, rules, simulations, planners, audits
├── data/                     Raw snapshots, processed contracts, evidence
├── models/                   Versioned serving-model metadata/artifacts
├── notebooks/                Walk-forward replay of the current season
├── scripts/                  Refresh and operational commands
├── tests/                    Backend correctness and regression suite
└── docs/                     Operations, decision history, and product visuals
```

## Product principles

1. **Recommendation first.** Analysis supports the decision instead of burying it.
2. **Points first.** The plan maximizes expected points, not rank.
3. **Rules are data.** Every scoring era is versioned and testable.
4. **No hidden hindsight.** Published simulations see only deadline-safe information, and known gaps are stated.
5. **No automatic FPL actions.** The manager remains in control.
6. **Evidence over hype.** Failed experiments stay failed; aggregates never hide a bad season.

## Contributing

1. Create a focused branch.
2. Add or update tests for every behavioral change.
3. Run the relevant quality gates.
4. Keep experimental models isolated until they pass multi-season acceptance.
5. Never commit credentials, local `.env` files, generated browser output, or private FPL account data.
6. Keep recommendations explainable by recording the data cutoff and rules contract used.

## Disclaimer

SquadMetric is an independent fantasy-football analytics project. It is not affiliated with, endorsed by, or sponsored by the Premier League or Fantasy Premier League. FPL rules, data, names, and marks belong to their respective owners. Recommendations are probabilistic and cannot guarantee a score, rank, or top-1% finish.

<p align="center">
  <strong>Build the plan. Understand the trade-off. Make the call.</strong>
</p>
