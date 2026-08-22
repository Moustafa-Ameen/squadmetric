# P7 — GW1 Decision Hardening

## Objective

Make the live 2026/27 opening-squad recommendation auditable under role,
availability, captaincy, and bench uncertainty without replacing the validated
production policy silently.

## Official context

- The GW1 deadline is 21 August 2026 at 18:30 BST, and player prices remain
  locked until that deadline.
- FPL allows unlimited changes to the opening squad before GW1.
- Official preseason guidance highlights late World Cup returns, eight new
  managers, new signings, and final friendlies as material role evidence.
- Official Scout guidance recommends considering fixture rotation for cheap
  players rather than treating a non-playing bench as harmless.

Sources:

- https://www.premierleague.com/en/news/4680462/whats-new-in-202627-fantasy-price-change-predictor
- https://www.premierleague.com/en/news/4680722/fpl-is-live-pick-your-202627-squad-now/
- https://www.premierleague.com/en/news/4679613
- https://www.premierleague.com/en/news/4677454/how-to-rotate-your-cheap-players-in-fpl-to-get-best-fixtures-every-week

## Implementation

- Added deterministic `maximum_points`, `balanced`, and `safe` opening-squad
  profiles using the same live projections, budget, formation, and club limits.
- Kept `balanced` as the production default. Other profiles are explicitly
  experimental.
- Added a hard optimizer exclusion for players whose official availability is
  zero, even if their point projection is high.
- Added minimum reliable-player constraints for balanced and safe profiles.
- Added profile comparisons for GW1 points, eight-Gameweek points, squad start
  probability, outfield bench reliability, captaincy, bank, and player changes.
- Added a decision audit covering unavailable selections, low-reliability
  starters and bench players, vice-captain fallback, and first-bench cover.
- Changed the website's preseason default from the experimental three-week
  horizon to the production eight-week horizon.
- Added profile controls and visible bench-risk warnings to the planner.

## Live comparison at the implementation cutoff

| Profile | GW1 xP | Eight-GW xP | Mean squad start | Outfield bench start | Changes vs balanced |
|---|---:|---:|---:|---:|---:|
| Maximum points | 62.20 | 487.78 | 78.82% | 28.63% | 0 |
| Balanced | 62.20 | 487.78 | 78.82% | 28.63% | 0 |
| Safer depth | 61.85 | 486.20 | 82.04% | 47.42% | 4 |

The safer-depth profile sacrifices 0.35 projected GW1 points and 1.58 projected
points over eight Gameweeks at this cutoff. It improves estimated bench
reliability materially, but still contains one sub-35% player and therefore is
not promoted automatically.

Maximum-points and balanced currently converge to the same squad. This is a
valid finding, not evidence that the alternatives are wired incorrectly: the
API persists each profile's independent metrics and selected state.

## Acceptance boundary

P7 changes the decision interface and adds safety constraints. It does not claim
that safer depth is historically superior, because current preseason role
evidence cannot be replayed honestly at old deadlines. Balanced remains the
production default; all profile changes require a final refresh after the last
preseason lineups and deadline team news.
