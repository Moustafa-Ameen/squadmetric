# Phase P2 — Points-Loss and Decision-Regret Audit

## Status

Complete. This original audit is superseded for production prioritization by
`phase-post-recovery-points-loss-audit.md`, which audits the corrected accepted
scorecard across all three supported seasons.

P2 adds an auditable layer around completed historical simulations. It does not
change models, transfers, captaincy, chips, or accepted benchmark history.

## Implemented

- Exact per-Gameweek and per-season reconciliation of realistic gross points,
  hit costs, net points, and cumulative points.
- Hindsight captain/vice regret using the effective post-autosub XI, including
  the correct extra multiplier for Triple Captain.
- Legal hindsight-XI and ordered-bench diagnostics when the required 15-player
  squad state is persisted.
- One-Gameweek selected-transfer diagnostics using stable outgoing/incoming
  player IDs.
- Expansion of every persisted expected chip counterfactual, with realized gain
  attached only to the selected branch.
- A source-backed historical rank-reference contract with explicit bounded,
  approximate, and unavailable states.
- Separate audit artifacts and hashes; permanent benchmark history is untouched.

Future benchmark rows now persist:

```text
squad_ids
selected_starting_ids
selected_bench_ids
realistic_starting_ids
realistic_autosub_ids
realistic_formation
outgoing_id
incoming_id
```

Legacy simulations remain readable. Missing state is never reconstructed from
names or squad hashes.

## Definitions and safeguards

- Exact accounting is kept separate from hindsight regret.
- Hindsight regret is an upper-bound diagnostic, not a production score.
- Overlapping buckets are never summed into a hypothetical season total.
- Chip timing regret remains unavailable until legal cross-Gameweek replay
  exists.
- Missed profitable hits remain unavailable until all legal point-in-time
  transfer branches are persisted or replayed.
- Initial-squad regret requires a full-season continuation from alternative
  legal opening squads.
- Availability/minutes and projection-ranking loss require player-level
  deadline projections that current simulation rows do not persist.

## 2025/26 validation

The completed production simulation at
`data/processed/simulations/20260726T144852Z-production-aee1a009` was audited:

- 38 Gameweeks reconciled exactly.
- Gameweek net points summed to 2,265, matching the season summary.
- No cumulative reconciliation failures occurred.
- Captain/vice hindsight regret was 215 points. This is non-additive and must
  not be interpreted as a directly attainable score increase.
- The older artifact did not contain full squad, ordered bench, or transfer
  player IDs, so those regret buckets are explicitly partially unavailable.
- The score is 54 points below the verified known-inside 2025/26 score example
  and 31 points below the verified known-outside score example. The exact
  top-1% points cutoff is not asserted.

## Commands

```powershell
.\.venv\Scripts\python.exe -m fpl_intelligence.points_loss_audit --simulation-dir data/processed/simulations/<run-directory>
```

## Acceptance

P2 passes because:

- score accounting reconciles exactly;
- every planned loss bucket has an auditable definition and availability state;
- no unsupported regret is fabricated;
- rank references preserve sources and retrieval metadata;
- focused tests and persistence regression tests pass;
- Ruff is clean for the changed P2 code.

The original P2 review gate was completed. Current follow-up is tracked in the
post-recovery audit.
