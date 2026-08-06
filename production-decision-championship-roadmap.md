# Production Decision Championship Roadmap

## Objective

Turn the technically reliable FPL Intelligence platform into a measurably
top-1%-oriented decision system. Promotion decisions are based on realistic
historical season points and live deadline audits, not forecast error alone.

No phase may claim that top 1% is guaranteed. Football outcomes contain
irreducible uncertainty, and historical points are not identical to rank.

## Starting position

- The 2026/27 rules, player, team, fixture, price, and artifact contracts are
  live and fail closed.
- The production portfolio routes Ridge to transfers and captaincy and Gradient
  Boosting to chip valuation.
- Historical scoring supports transfers, hits, legal squads, lineups,
  autosubs, realistic captaincy, and season-specific chips.
- Historical benchmark evidence exists, but there is no safe self-service
  command or complete points-loss decomposition.
- New and unmatched 2026/27 players still rely heavily on preseason priors.

## P1 — Self-service historical simulation

Create a read-only simulation command with explicit presets:

- `production`: active production model portfolio, complete beam planner, and
  historical chips.
- `control`: rollback Ridge-only portfolio with the same planner and chips.
- `no-chip`: active transfer/captain models with chips disabled.
- `diagnostic-no-transfers`: static-squad diagnostic only.

Every run must:

- use only point-in-time data;
- validate requested seasons and historical rules;
- default to 2023/24, 2024/25, and 2025/26;
- leave permanent benchmark history unchanged;
- write a run manifest, season summary, and Gameweek decisions;
- record dataset/configuration hashes, commit, model routing, rules versions,
  captaincy, transfers, hits, and chips;
- print realistic points per season clearly.

P1 passes when focused tests, Ruff, and a representative real simulation pass.

## P2 — Points-loss and decision-regret audit

Decompose each completed season into recoverable losses:

- initial-squad regret;
- captain and vice-captain regret;
- starting-XI, bench-order, and autosub regret;
- transfer selection and timing regret;
- profitable hits missed and bad hits taken;
- chip timing and chip-preparation regret;
- blank/double Gameweek loss;
- availability/minutes error;
- projection ranking error.

Counterfactuals must remain legal and point-in-time safe. Hindsight-oracle
figures are diagnostic upper bounds, never production scores.

P2 passes when every realistic season total reconciles exactly to its Gameweek
rows and every loss bucket has an auditable definition.

P2 must also add a rank-relative reference table:

- verified final total-team count per season;
- verified points around the top-1% rank boundary;
- simulated score margin above or below that boundary;
- source and retrieval metadata;
- explicit `unavailable` status where a trustworthy historical rank snapshot
  cannot be obtained.

Rank-boundary data is an evaluation reference only and must never leak future
ownership or outcomes into decisions.

## P3 — Initial-squad championship

Replace the simple all-15-player points objective with a multi-objective,
multi-Gameweek opening-squad tournament.

Optimize:

- starting-XI and captain points over 3, 5, and 8 Gameweeks;
- expected minutes and uncertainty;
- bench spend and playable coverage;
- early transfers and fixture swings;
- price structure and future flexibility;
- rotation pairings;
- early Wildcard scenarios;
- promoted-team and new-player uncertainty.

Evaluate candidate opening squads through full-season continuation, not only
GW1 projections.

P3 recovery outcome (2026-08-01): the cross-season element-ID join has been
removed from executable production paths. Against the corrected identity-safe
control, the cold-start-safe 8-GW policy scores 0, +198, and +12 points across
2023/24, 2024/25, and 2025/26. It improves two seasons, regresses none, and adds
210 aggregate realistic points, so it is promoted to the self-service
production simulator and live initial-squad endpoint. See
`phase-performance-recovery-initial-squad.md`.

## Post-recovery decision-loss gate

The corrected 6,651-point scorecard has now been audited across all 114
Gameweeks. Captaincy has the largest measured hindsight upper bound, but the
audit also found a prior correctness blocker in chip timing: all 18 selected
chips were assigned zero future opportunity cost and all four Free Hits
realized zero incremental points.

Completed on 2026-08-06. Same-chip save valuation now keeps the exact chip slot
available in future counterfactuals, respects its legal window, and values
future Bench Boost, Triple Captain, Free Hit, and Wildcard opportunities.
Explicit beam-horizon opportunities are not charged twice. The realistic
three-season scorecard changed from 2,321 / 2,194 / 2,136 to 2,321 / 2,360 /
2,249: two seasons improved by 166 and 113 points with no regression.

The phase also corrected squad-changing-chip audit semantics. Free Hit direct
Gameweek gains were +10, +3, +28, and +64 rather than the previously persisted
zeros; Wildcard continuation value remains separate from its direct Gameweek
gain. The repair passes the post-recovery gate, while its longer historical
runtime remains a documented optimization target. See
`phase-chip-save-value-correctness.md`.

## P4 — Consumer-specific model tournament

Run separate champion/challenger tournaments for:

- transfers;
- captaincy;
- chips;
- minutes/availability;
- initial squad;
- starting XI and bench order;
- hit decisions.

Candidates may include Ridge, Gradient Boosting, calibrated component models,
and carefully justified ensembles. A model is promoted only when its downstream
decision points improve under the complete simulator.

P4 completed on 2026-08-06/07. The tournament first screened candidates with
chips disabled, then replayed four finalists through the complete chip-aware
simulator across 2023/24, 2024/25, and 2025/26. Every full-stage comparison used
the same promoted opening squad and changed one declared consumer assignment.
The production champion reconciled exactly to 2,321 / 2,360 / 2,249 realistic
points.

The full-stage realistic deltas were:

| Candidate | Consumer | 2023/24 | 2024/25 | 2025/26 | Aggregate | Outcome |
|---|---|---:|---:|---:|---:|---|
| Ridge chip model | chips | +11 | +126 | -38 | +99 | validated challenger; not auto-promoted |
| Gradient transfer model | transfers | -113 | +176 | -156 | -93 | rejected |
| Gradient lineup model | starting XI | -1 | +12 | -26 | -15 | rejected |
| horizon-value hit policy | hits/beam | -103 | -222 | -41 | -366 | rejected |

The Ridge chip challenger passes the predefined two-season and seasonal-loss
gate, but its 38-point regression in the latest eight-chip validation regime is
a current-season caveat. Production therefore remains Ridge transfer + Ridge
captain + Gradient chip + Ridge lineup until an explicit integrated promotion
review; P4 itself does not mutate routing.

The hit-policy result is not evidence that taking a profitable -4 can never
work. It selected zero hits, while the policy also reduced the beam transfer cap
from six to two and therefore changed non-hit decisions. It is rejected and
must be redesigned as a truly isolated hit comparison in P7. Component,
team-component, and availability/minutes candidates failed screening and remain
deferred to their dedicated rework phases. See
`phase-p4-consumer-model-tournament.md`.

## P5 — New-player and promoted-team intelligence

Replace generic position priors with timestamped evidence:

- prior-league minutes and production;
- competition-strength translation;
- expected role and starting probability;
- penalties and set pieces;
- squad competition and transfer fee;
- manager tactics and formations;
- preseason lineups and minutes;
- promoted-team attack and defence priors.

Source observations must include publication and observation timestamps.
Unknown information remains uncertain rather than being silently zero-filled.

## P6 — Availability and role championship

Build calibrated probabilities for:

- starting;
- substitute appearances;
- conditional minutes;
- reaching 60 minutes;
- injury and suspension availability;
- rotation and role changes.

Evaluate decision points, calibration, and chip interaction. The failed M2/M9
variants remain experimental until they beat the accepted control.

## P7 — Joint transfer, hit, and chip optimization

Strengthen the complete receding-horizon decision search:

- multiple transfers and deliberate hits;
- free-transfer banking;
- Wildcard permanence;
- Free Hit reversion;
- Bench Boost preparation;
- Triple Captain opportunity cost;
- captain and vice-captain selection;
- future squad flexibility;
- blank/double and postponement scenarios.

Runtime pruning must not remove the current squad, key low-cost enablers, or
high-upside fixture-regime candidates.

## P8 — Live 2026/27 shadow championship

At every deadline, freeze:

- official data and rules hashes;
- news cutoff;
- projections;
- squad, transfer, hit, captain, bench, and chip decisions;
- rejected legal alternatives.

After final scoring corrections, compare active and control decisions. Never
rewrite a pre-deadline recommendation after outcomes are known.

## P9 — Final promotion gate

A production challenger must satisfy all of the following:

- zero leakage and rules-contract failures;
- exact reconciliation of Gameweek and season scores;
- improvement in at least two completed seasons;
- no severe seasonal regression;
- no severe blank/double Gameweek regression;
- better relevant decision metrics, not MAE alone;
- deterministic repeated runs;
- explicit rollback configuration;
- acceptable live shadow performance once enough 2026/27 deadlines exist.
- a reported margin against the verified historical top-1% points boundary,
  without treating that historical boundary as a future guarantee.

The accepted production portfolio remains active until a challenger passes the
entire gate.

## Operating sequence

Implement one phase at a time. Run focused tests, full regression tests when
the phase changes shared logic, Ruff, and a real reconciliation before starting
the next phase.
