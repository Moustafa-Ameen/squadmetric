# Full Repository Production Audit — 2026-08-16

## Verdict

Production-readiness gate passed for the current recommendation-only 2026/27
application. The accepted model portfolio, beam decision control, scoring
rules, chip logic, historical benchmark history, and automatic post-Gameweek
workflow were not replaced by this cleanup.

No audit can prove that software contains zero future defects. This audit found
and repaired four concrete production risks, removed obsolete and rejected
material, and passed every currently available automated gate.

## Defects repaired

1. **Frontend dependency vulnerabilities**
   - Upgraded Next.js and `eslint-config-next` from 16.2.10 to 16.3.1.
   - Refreshed vulnerable transitive packages.
   - Full npm audit now reports zero known vulnerabilities.

2. **Stale readiness cache**
   - Readiness was cached using only the manifest modification time.
   - A model or referenced artifact could change while an earlier `ready`
     result remained cached.
   - The cache key now includes every manifest path and every model artifact's
     path, modification time, and size.

3. **Non-JSON-safe API records**
   - Floating-point `NaN` values could survive the pandas conversion and reach
     FastAPI responses.
   - Dataset records now convert missing values to real JSON `null` values.

4. **Malformed official FPL responses**
   - Invalid JSON from the upstream FPL service previously escaped as a generic
     server error.
   - It now fails as the same explicit temporary-unavailability 503 contract as
     FPL timeout and HTTP failures.

## Removed production clutter

### Deleted application code

- Retired Streamlit dashboard and its loader.
- Rejected standalone captaincy experiment runner and tests.
- Rejected standalone lineup/autosub experiment runner and tests.
- Retired dashboard-only test.

The Next.js/FastAPI application is the sole supported user interface. Shared
benchmark and rule code was retained where production or reproducibility still
depends on it. Failed model modes remain unreachable from production defaults;
their small shared implementation was not deleted when doing so would weaken
the accepted historical benchmark or make prior acceptance results impossible
to reproduce.

### Deleted generated and rejected artifacts

- `frontend.zip`, `data.zip`, and `src.zip`.
- Old development `.next` cache; replaced by a clean production build.
- Entire rejected `analysis/` experiment-output tree.
- Rejected Random Forest model artifact.
- Generated `step4_predictions.csv` and `step6_backtest_predictions.csv`.
- Failed M9 output histories.
- Obsolete simulation/test stdout and stderr logs.
- Python, pytest, Ruff, Playwright, and Next development caches.
- Stale 631 MB Git LFS object left by the old frontend archive.
- Retired Streamlit, notebook, plotting, Arrow, and associated Python packages.
- Superseded or rejected phase reports for M7, M9, M10, P2, captaincy,
  lineup/autosub, multi-transfer, generic projection calibration, transfer
  branch ranking, and transfer-state value.

Offline prediction CSVs can still be regenerated from the retained historical
pipeline if a future evaluation explicitly needs them. They are not required
by the production website.

## Ongoing space protection

Identical immutable official snapshots now reuse the same filesystem payload
through hard links while preserving a separate timestamped metadata record for
every retrieval. Eighteen existing duplicates were deduplicated, saving about
12.6 MB immediately and preventing repeated unchanged daily payloads from
consuming full duplicate storage.

Approximate logical repository size:

- Before audit: 3,548 MB.
- After audit with runnable dependencies and a production frontend build:
  1,008 MB.
- Reduction: about 2,540 MB, or 72%.

The retained space is primarily the runnable Node dependencies, Python virtual
environment, official/historical data, and the verified frontend production
build.

## Verification evidence

- Python full suite: **273 passed**.
- Focused new operational tests: passed.
- Ruff across `src`, `api`, `tests`, and `scripts`: clean.
- Python compile-all: clean.
- `pip check`: clean.
- Python vulnerability audit: zero known vulnerabilities in installed
  auditable packages.
- npm production and full dependency audit: zero known vulnerabilities.
- ESLint: clean.
- Frontend search tests: 3 passed.
- Next.js optimized production build: passed, including TypeScript and all 13
  generated routes.
- Real artifact readiness with model deserialization: `ready`.
- Official 2026/27 post-Gameweek dry run: clean, with no provisional events
  ingested.
- API smoke tests passed for health, readiness, players, 15-player opening
  squad, and portfolio status.
- Windows daily refresh task remains registered, enabled, and `Ready`.
- Zero zip archives remain in the repository.
- No stale source or documentation references to deleted components remain.

## Production configuration retained

- Default portfolio: `r2_validated`.
- Transfer model: Ridge Regression.
- Captain model: Ridge Regression.
- Chip model: Gradient Boosting Regressor.
- Accepted deterministic beam planner remains the live decision engine.
- Same-deadline multi-transfer and horizon-value challenger behavior remains
  disabled by production defaults.
- Recommendation-only behavior remains enforced; no automatic FPL action is
  introduced.
- Daily refresh remains at 08:00 local time.

## Remaining operational note

The scheduled refresh has no private FPL team ID configured. Public data,
finalized-Gameweek ingestion, model refresh, and serving publication will run.
After GW1, private manager-specific evidence capture will be skipped until the
task is re-registered with `-TeamId`.
