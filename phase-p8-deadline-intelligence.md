# P8 — Deadline Intelligence and Shadow Validation

## Outcome

The daily 2026/27 refresh now persists the recommendation itself, not only its
input data. This creates a no-hindsight ledger of what the platform advised at
each cutoff and how the advice changed before GW1.

## Implemented

- Immutable balanced-profile recommendation snapshots.
- Stable hashes over squad, captain, vice-captain, profile alternatives, model
  portfolio, rules, source data, cutoff, and audit results.
- Drift reports for transfers in/out, captain and vice changes, bootstrap
  changes, and projected-point changes.
- A 24-hour artifact freshness contract.
- Detection of the next official deadline and time remaining.
- A final-24-hours refresh requirement.
- An operations endpoint with explicit freshness, deadline, shadow-capture, and
  final-team-news checklist items.
- Scheduled refresh failure when recommendation capture fails.

## Real capture

The first live snapshot was captured successfully on 7 August 2026:

- Season: 2026/27
- GW1 expected points: 62.2
- First snapshot: yes
- Squad drift: not applicable
- Data age at audit: 17.39 hours
- GW1 deadline: 21 August 2026 at 17:30 UTC
- Deadline blockers: none

## Commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh-2026-27.ps1
.\.venv\Scripts\python.exe -m scripts.capture_gw1_shadow
```

API:

```text
GET /api/operations/deadline-readiness
```

P8 does not auto-execute FPL changes. It records and audits recommendations so
the final human decision remains traceable and can be evaluated after GW1.
