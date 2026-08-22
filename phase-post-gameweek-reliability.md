# Post-Gameweek Reliability and Continuous Update Gate

## Outcome

Passed. The live 2026/27 workflow now updates public FPL data every day and
adds current-season training evidence only after an official Gameweek is both
`finished` and `data_checked`.

This phase changes operational reliability, not the accepted scoring strategy,
model family, transfer policy, captaincy policy, or chip policy.

## Implemented contract

- Detect finalized Gameweeks from the official bootstrap finalization flags.
- Select the latest immutable bootstrap snapshot whose cutoff is on or before
  the relevant official deadline.
- Build a separate finalized-only current-season player/Gameweek table at
  `data/processed/live_2026_27_player_gw.csv`.
- Keep historical benchmark data immutable and separate from live learning.
- Append idempotently by season, Gameweek, and stable player ID.
- Reject conflicting payloads, skipped Gameweeks, provisional flags, hash
  mismatches, post-deadline feature cutoffs, and wrong-season payloads.
- Preserve official event-live payloads and metadata as immutable hash-tracked
  snapshots.
- Retrain the already accepted serving-model family on historical data plus
  finalized current-season rows. No candidate architecture is promoted here.
- Publish history, models, official snapshots, and frozen decision outcomes in
  one rollback-protected file transaction.
- Refresh prices, fixtures, availability, rankings, rules, and manifests even
  when no new Gameweek is finalized; do not retrain in that case.
- Keep direct full-model refreshes safe by retaining previously finalized live
  rows rather than accidentally dropping them.
- Stop GW1-only shadow capture once the first deadline has passed.
- Continue public refreshes without a team ID after GW1, while explicitly
  warning that private planner-evidence capture was skipped.

## Operational state

The Windows scheduled task `FPL Intelligence 2026-27 Daily Refresh` is
registered, enabled, and ready. It runs daily at 08:00 local time and invokes
`scripts/refresh-2026-27.ps1` from this repository.

No team ID was supplied during this phase. Therefore public data ingestion,
official finalization detection, model refresh, and artifact publication will
run automatically, but post-GW1 private planner snapshots will be skipped until
the task is re-registered with `-TeamId`.

## Verification

- Focused post-Gameweek, artifact, and evidence tests: 22 passed.
- Full repository test suite: 286 passed.
- Focused Ruff checks: clean.
- PowerShell parser checks: clean for both refresh scripts.
- Official API dry run on 2026-08-16: no finalized Gameweeks, no files
  published, and no model retraining requested.
- Historical benchmark-history file: unchanged.
- Existing current-season artifact readiness: passed with real model loading.

## Operator commands

Safe no-write validation:

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.post_gameweek_refresh --season 2026-27 --dry-run
```

Run the complete refresh manually:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1
```

Enable private post-GW1 decision evidence by replacing `YOUR_TEAM_ID`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-daily-refresh.ps1 -TeamId YOUR_TEAM_ID
```

## Promotion decision

Operational update pipeline accepted. No scoring-performance claim is made by
this phase. New live outcomes improve the training evidence available to the
fixed model over the season, but each update remains gated by official
finalization, artifact readiness, deterministic hashes, and rollback safety.
