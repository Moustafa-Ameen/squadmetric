# Performance Recovery - Identity-Safe Initial Squad

## Status

Complete and promoted.

This recovery removed the invalid cross-season FPL element-ID join from the
production historical opener, established an identity-safe control, and
promoted a cold-start-safe 8-Gameweek opening policy.

## Correctness repair

FPL `player_id`/`element` values are season-local. The previous preseason
scorer joined prior-season totals to current-season players using those IDs.
The recovery now:

- matches prior-season evidence only by an unambiguous normalized player name;
- marks ambiguous or unmatched players as uncertain rather than borrowing a
  different player's history;
- records the prior player ID only as audit metadata after a safe name match;
- uses current price/ownership and position priors for unmatched players;
- passes a frozen 15-player override into every simulator path so identical
  opening squads have identical continuation contracts;
- labels the identity-safe scorer as the rollback control.

## Accepted production policy

`horizon_8_flexible_cold_start_safe`

- If at least one earlier supported season exists, use the reviewed
  multi-objective 8-GW MILP opener.
- If no earlier supported season exists, use the identity-safe value baseline.
- The live 2026/27 initial-squad endpoint defaults to the 8-GW policy because
  prior completed seasons and trained artifacts are available.
- Explicit 3-GW and 5-GW API requests remain experimental.

The cold-start rule is input-driven and point-in-time safe. It does not inspect
season outcomes.

## Definitive realistic scorecard

All totals include realistic transfers, captaincy, hits, autosubs, historical
chips, and season rules.

| Season | Identity-safe control | Production policy | Delta |
| --- | ---: | ---: | ---: |
| 2023/24 | 2,321 | 2,321 | 0 |
| 2024/25 | 1,996 | 2,194 | +198 |
| 2025/26 | 2,124 | 2,136 | +12 |
| **Total** | **6,441** | **6,651** | **+210** |

Acceptance:

- improved seasons: 2;
- regressed seasons: 0;
- worst season delta: 0;
- aggregate improvement: +210 points;
- severe regressions: 0;
- result: passed.

This is the first accepted scoring improvement produced after replacing the
invalid historical control. It does not guarantee a top-1% rank.

## Reconciliation

2023/24 production artifact:

`data/processed/simulations/performance-recovery-production-v3-2023-24`

2024/25 and 2025/26 tournament artifact:

`data/processed/initial_squad_tournaments/performance-recovery-2024-2025`

Verified:

- 38 Gameweek rows for every season-policy path;
- every Gameweek sum equals its season continuation total;
- every final cumulative score equals the season total;
- zero model/captain training-cutoff violations;
- one stable opening-squad hash per path;
- all tournament artifact SHA-256 values match the run manifest;
- checkpoint files were removed after successful finalization.

## Production changes

- The self-service `production` and `no-chip` presets use the accepted
  cold-start-safe policy.
- The `control` and static diagnostic presets use the identity-safe baseline.
- Simulation manifests and season summaries persist the opening policy,
  version, and squad hash.
- The live initial-squad endpoint defaults to horizon 8 and reports policy name,
  version, and validation status.
- Future P3 tournaments use `identity_safe_value` as their baseline; the
  misleading legacy baseline label has been removed from executable code.

P4 has not started.
