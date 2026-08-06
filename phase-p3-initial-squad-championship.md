# Phase P3 - Initial-Squad Championship

## Status

Complete. The original invalid-control tournament promoted no challenger, but
its required correctness recovery is now complete and has promoted the
cold-start-safe 8-GW policy. See
`phase-performance-recovery-initial-squad.md`.

The implementation, focused tests, three-season chip-aware tournament, artifact
reconciliation, and acceptance gate are complete. The result is a valid
negative result: every challenger improved 2023/24, but every challenger
regressed severely in both 2024/25 and 2025/26.

The original table below is retained as historical evidence of why the legacy
control was rejected. It is superseded for production decisions by the
identity-safe recovery scorecard.

## What P3 implemented

- Identity-safe prior-season matching by normalized player name. Season-local
  FPL element IDs are never treated as cross-season player identities.
- Deterministic 3-, 5-, and 8-Gameweek opening-squad policies.
- Joint MILP selection of the legal 15-player squad, starting XI, and captain.
- Objectives covering expected points, starting probability, uncertainty,
  bench depth, value, future transfer pressure, promoted-team uncertainty, and
  unmatched/new-player uncertainty.
- Early-Wildcard scenarios for the 3- and 5-Gameweek policies.
- Complete 38-Gameweek continuation with the production projection portfolio,
  realistic transfers, captaincy, hits, autosubs, and historical chips.
- Per-candidate checkpointing and safe resume.
- Deterministic continuation reuse when two candidates have the exact same
  opening-squad hash.
- Persisted projected candidates, candidate squads, projected plans, Gameweek
  decisions, continuation totals, acceptance results, and a hashed run
  manifest.

## Confirmed legacy identity defect

The old preseason scorer joins a prior season to the current season using
`player_id`. FPL element IDs are season-local and cannot be used this way.

The processed historical table confirms:

| Transition | Overlapping IDs | Same player | Wrong player |
| --- | ---: | ---: | ---: |
| 2023/24 to 2024/25 | 615 | 0 | 615 |
| 2024/25 to 2025/26 | 690 | 0 | 690 |

The legacy table is retained only as an audit record of the frozen comparison
that exposed the defect. The ID-unsafe preseason method is no longer an
executable benchmark or production option.

The legacy opening squad also left unusually large unused budgets:

| Season | Squad cost | Initial bank |
| --- | ---: | ---: |
| 2023/24 | 99.5 | 0.5 |
| 2024/25 | 75.5 | 24.5 |
| 2025/26 | 77.5 | 22.5 |

This was one reason P3 tested minimum-spend and flexibility-aware policies.

## Tournament results

All scores below are realistic, chip-aware full-season points.

| Season | Legacy control | Identity-corrected | 3-GW attack | 5-GW balanced | 8-GW flexible |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023/24 | 2,298 | 2,345 | 2,310 | 2,310 | 2,310 |
| 2024/25 | 2,526 | 1,996 | 1,988 | 2,053 | 2,194 |
| 2025/26 | 2,265 | 2,124 | 2,153 | 2,064 | 2,136 |

Per-candidate deltas against the frozen control:

| Candidate | 2023/24 | 2024/25 | 2025/26 | Aggregate | Severe regressions | Passed |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Identity-corrected | +47 | -530 | -141 | -624 | 2 | No |
| 3-GW attack | +12 | -538 | -112 | -638 | 2 | No |
| 5-GW balanced | +12 | -473 | -201 | -662 | 2 | No |
| 8-GW flexible | +12 | -332 | -129 | -449 | 2 | No |

No candidate meets the requirement to improve at least two seasons without a
severe seasonal regression. Aggregate masking is not used.

## Reconciliation

The completed production tournament is stored at:

`data/processed/initial_squad_tournaments/p3-production-checkpointed-20260728`

Verified properties:

- 15 continuation rows: five policies across three seasons.
- 570 Gameweek rows: exactly 38 for every season-policy path.
- Every Gameweek sum equals its persisted season total.
- Every final realistic cumulative score equals its persisted season total.
- Zero points/captain model training-cutoff violations.
- Every data cutoff is season and Gameweek shaped.
- Every persisted artifact SHA-256 matches the run manifest.
- The 2025/26 legacy control reconciles to the existing 2,265-point reference.
- No checkpoint files remain after successful finalization.

## Interpretation

P3 disproves two tempting conclusions:

1. Spending almost the full budget is not automatically better.
2. Correcting player identity is necessary for validity but is not sufficient
   to produce a strong opener.

The challengers used point-in-time-safe inputs, but the preseason projection
signal for transferred, promoted, and otherwise unmatched players is still too
weak. A full-budget optimizer can concentrate money into confidently wrong
priors and create a squad that the one-transfer-per-Gameweek continuation
cannot repair quickly.

The correct outcome is therefore non-promotion. P3's safe optimizer and
identity layer remain available for future challengers, while the failed
policies remain experimental.

## Required follow-up

Before treating historical opening-squad scores as production-quality evidence,
the project needs a correctness-first P3 recovery:

- remove cross-season element-ID joins from the historical preseason control;
- establish an honest identity-safe baseline even if its displayed score is
  lower;
- improve new-player, promoted-team, role, and preseason priors;
- re-run the same frozen championship against that corrected baseline;
- only then consider routing an accepted opener to the live API or production
  simulator.

The required follow-up is complete. P4 has not started.
