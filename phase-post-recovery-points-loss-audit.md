# Performance Recovery - Post-Recovery Points-Loss Audit

## Status

Complete. No downstream captaincy, lineup, transfer, or chip policy was changed
in this phase.

## Decision

The next intervention should repair and revalidate chip save-value and timing
before beginning a broad consumer-model tournament.

Captaincy has the largest measured hindsight upper bound, but that does not
prove those points were forecastable. Chip timing has a directly verified
planner defect: every selected chip in the accepted three-season scorecard was
assigned zero future opportunity cost, because the current search evaluates
future legality after removing the consumed chip instead of valuing the same
chip if saved.

## Audited production scorecard

The audit loads only the accepted production paths:

- 2023/24: cold-start-safe identity fallback;
- 2024/25: `horizon_8_flexible`;
- 2025/26: `horizon_8_flexible`.

All 114 Gameweeks reconcile exactly:

| Season | Realistic points | Verified inside score | Margin |
| --- | ---: | ---: | ---: |
| 2023/24 | 2,321 | unavailable | unavailable |
| 2024/25 | 2,194 | 2,508 | -314 |
| 2025/26 | 2,136 | 2,319 | -183 |

The 2024/25 margin is directionally useful but not fully like-for-like because
the historical top-1% reference includes Assistant Manager while the accepted
scorecard did not activate that historical-only chip. Assistant Manager should
not return to the current-season product.

## Decision diagnostics

These values overlap and must not be added to the simulated score.

| Decision area | 2023/24 | 2024/25 | 2025/26 | Aggregate | Evidence class |
| --- | ---: | ---: | ---: | ---: | --- |
| Captaincy | 254 | 226 | 283 | 763 | hindsight upper bound |
| Starting XI | 134 | 183 | 229 | 546 | hindsight upper bound |
| Selected transfers | 37 | 27 | 31 | 95 | one-GW partial hindsight |

Captaincy is the largest measured opportunity in all three seasons. It should
be the first model consumer tested after the chip correctness repair, but the
763 points are not an attainable improvement claim.

## Verified chip failure

- 18 chip activations were selected across the three seasons.
- 18 of 18 persisted `future_opportunity_cost = 0`.
- All four selected Free Hits realized exactly zero incremental Gameweek points.
- First-half non-Wildcard inventories were exhausted by GW5, GW6, and GW6.
- The first Bench Boost returned 2, 2, and 7 points respectively.
- Wildcard same-Gameweek realized gain remains intentionally unavailable; its
  value requires continuation replay.

The zero save-value rate is not merely an unlucky-outcome observation. Code
inspection confirms that `_future_opportunity_cost` evaluates future legal
chips from `next_chip_state`, where the chip being assessed has already been
removed. It therefore cannot compare using that same chip now versus saving it.

## Audit hardening

The phase added:

- a canonical loader for the split post-recovery scorecard artifacts;
- exact 38-Gameweek completeness and duplicate checks per season;
- active Free Hit squad reconstruction from selected XI plus ordered bench;
- season-local, latest-prior identity metadata for players absent from a
  Gameweek table;
- valid captain regret when both captain and vice fail to play;
- a lineup oracle that validates formation and position quotas without
  incorrectly rejecting an owned squad because its current price exceeded the
  original budget or a real transfer changed club counts;
- persisted chip usage and decision-opportunity artifacts;
- a self-service `--recovery-scorecard` command.

## Artifacts

`data/processed/points_loss_audits/post-recovery-production-v1`

The directory contains:

- `points_loss_gameweeks.csv`;
- `points_loss_buckets.csv`;
- `decision_opportunities.csv`;
- `chip_usage.csv`;
- `chip_counterfactual_audit.csv`;
- `rank_reference_evaluation.csv`;
- `points_loss_audit_manifest.json`.

## Next phase acceptance target

The chip repair must:

- compare each legal chip now against saving that same chip for future legal
  Gameweeks;
- assign a nonzero opportunity cost when a stronger future window exists;
- preserve exact no-chip reconciliation;
- materially delay weak early activations;
- produce nonzero Free Hit value or choose not to activate it;
- improve at least two seasons with no severe regression;
- keep current-season Assistant Manager disabled.

That repair must be reviewed before the captaincy consumer tournament begins.
