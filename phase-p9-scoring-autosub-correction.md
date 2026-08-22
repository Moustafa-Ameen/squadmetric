# P9 — 2026/27 Scoring-Regime and Autosub Correction

## Correction

The 2026/27 defensive-contribution thresholds did not change: defenders still
need 10 CBIT actions and midfielders/forwards need 12 CBIRT actions for two
points. The relevant change is BPS: CBI now earns one BPS per three actions
rather than one per two, reducing the likelihood that DC-heavy players also
receive bonus.

The previous live projection knew the `bps_v2_2026_27` rules label but did not
translate that delta into expected points. It also treated a player's prior
team role as transferable without uncertainty.

## Implementation

- Preserved starts, bonus, BPS, CBI, tackles, and recoveries from bootstrap.
- Added a transparent per-fixture BPS-v2 overlap penalty, capped at 0.35 points.
- Added a capped role-transition penalty to only the expected DC component when
  a player changed clubs.
- Persisted the two penalties, DC action rate, and team-change flag separately
  in every fixture projection.
- Replaced generic depth value with explicit linear autosub value:
  - a starting player receives full projection value;
  - a benched player receives projection × appearance probability × configured
    autosub activation probability;
  - full bench points are not counted unless a later Bench Boost decision uses
    them.
- Kept three profiles: maximum points (4% autosub), balanced (17%), and safe
  (24%). Balanced remains the production default.

## Live impact

- Previous balanced GW1 projection: 62.20
- Corrected balanced GW1 projection: 60.26
- Elliot Anderson: 4.71 → 4.34 GW1 xP
  - BPS-v2 adjustment: -0.04
  - Forest-to-Man City role uncertainty: -0.39
- Corrected balanced outfield-bench start probability: 54.82%
- Corrected maximum-points GW1 projection: 61.36
- Corrected safe GW1 projection: 59.74

Anderson remains selected after the correction. That is now an explicit model
decision under a reduced projection, not an accidental carry-forward of all
2025/26 DC and bonus value.

## Limitations

The bootstrap does not expose a `times_tackled` total, so the model cannot yet
give player-specific positive BPS adjustments for removal of the old tackled
penalty. The current correction is therefore conservative and must be reviewed
when richer Opta-style action data is available.
