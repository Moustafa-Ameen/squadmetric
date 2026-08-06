# Chip Save-Value Correctness Gate

## Status

Accepted on 2026-08-06. This phase changes chip planning and chip audit
semantics only. It does not start P4 or alter the transfer, captaincy, minutes,
component, or current-season Assistant Manager policy.

## Correctness repair

The beam previously evaluated future legality from the post-use chip state.
The chip under evaluation had already been removed, so its save value was
always zero and could be replaced accidentally by the value of another chip.

The repaired comparison now:

- retains the exact chip key and half-season slot in the saved counterfactual;
- checks the saved chip's own legal future window;
- values future Bench Boost bench points and Triple Captain captain points;
- builds legal future Free Hit squads and measures their one-Gameweek gain;
- builds legal future Wildcard squads and measures their permanent horizon
  gain;
- compares current and future horizon gains on the same basis;
- excludes future Gameweeks already searched explicitly by the beam, avoiding
  double-counted opportunity cost;
- remains deterministic for identical rules, projections, squad, and cutoff.

Focused tests first failed with the old implementation: saved Bench Boost and
Triple Captain returned zero, while Bench Boost borrowed a 20-point Triple
Captain opportunity. Those cases now pass, along with Free Hit, Wildcard,
expiry-window, and inside-beam-horizon tests.

## Three-season production replay

The isolated production preset retained the accepted opening-squad policy and
Ridge/Ridge/Gradient consumer portfolio. Permanent benchmark history was not
modified.

| Season | Accepted before | Repaired | Change |
|---|---:|---:|---:|
| 2023/24 | 2,321 | 2,321 | 0 |
| 2024/25 | 2,194 | 2,360 | +166 |
| 2025/26 | 2,136 | 2,249 | +113 |
| Total | 6,651 | 6,930 | +279 |

The acceptance rule passes: two seasons improve and none regress. This is a
historical decision-quality result, not a guarantee of a future top-1% rank.

Selected Free Hit timing changed from GW6 to GW12 in 2024/25 and from GW25 to
GW33 for the second 2025/26 slot. The 2023/24 selections did not move, so the
phase does not claim universal timing improvement.

## Realized chip audit correction

The benchmark previously defined `chip_realized_gain` only as a score
multiplier effect. That is valid for Bench Boost and Triple Captain but forces
Free Hit and Wildcard to zero because those chips change the squad rather than
the score multiplier.

The benchmark now compares a squad-changing chip's active squad score with the
retained no-chip squad score and persists `active_squad_ids` plus the true
active-squad hash. Direct realistic Free Hit gains reconstructed with the same
point-in-time transfer and captain models were:

| Season | Gameweek | Direct realistic gain |
|---|---:|---:|
| 2023/24 | 2 | +10 |
| 2024/25 | 12 | +3 |
| 2025/26 | 6 | +28 |
| 2025/26 | 33 | +64 |

Wildcard direct Gameweek gain is now measurable too, but its full value still
requires continuation comparison because its squad change is permanent.

## Controls and artifacts

Fresh chips-disabled controls using the same recovered opening-squad policy
produced 2,047 / 2,089 / 1,876 with zero chips and zero chip gain. The repair's
planner changes are unreachable in no-chip mode. A repeated isolated run
matched all three summaries and all 92 comparable fields across 114 Gameweek
rows exactly; only isolated run IDs/keys differed. No earlier artifact used the
same three opening-squad hashes and no-chip preset.

Isolated artifacts:

- `data/processed/simulations/chip-save-value-repair-2023-24`;
- `data/processed/simulations/chip-save-value-repair-2024-2026`;
- `data/processed/simulations/chip-save-value-no-chip-control`.
- `data/processed/simulations/chip-save-value-no-chip-control-repeat`.

The three chip-aware replays took about 38 minutes in total. This is acceptable
for the one-off gate but too slow for frequent experimentation. Future work may
memoize or safely prune future squad optimizations, but must reproduce these
decisions before replacing this accepted implementation.

## Decision

The chip correctness blocker before P4 is closed. The next phase is P4's
consumer-specific tournament, beginning with captaincy because the post-
recovery audit identified it as the largest measured decision-loss bucket.
P4 must still be started only after user confirmation.
