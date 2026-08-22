# P10 — Calibration and Opening-Squad Robustness

## Status

Implemented and quality-gated on 7 August 2026. P10 hardens the live GW1
recommendation; it does not claim that a preseason squad is certain or that a
top-1% finish is guaranteed.

## Historical autosub calibration

The calibration uses 110 non-Bench-Boost Gameweeks from the accepted
2023/24, 2024/25, and 2025/26 decision artifacts.

- At least one autosub was required in 49.09% of Gameweeks.
- The mean was 0.6818 autosubs per Gameweek.
- Mean bench-slot activation was 17.05%, replacing the previous 14% estimate.
- Activation by ordered bench slot was 36.36%, 21.82%, 7.27%, and 2.73%.
- The selected-starter nonappearance rate was 6.20%.

Nonappearance was materially different by point-in-time reliability:

| Reliability band | Selections | Nonappearance |
| --- | ---: | ---: |
| High | 1,108 | 5.23% |
| Medium | 94 | 18.09% |
| Low | 43 | 11.63% |

The low-reliability sample is small, so the non-monotonic medium/low result is
reported rather than smoothed into a false precision claim. By position, the
observed nonappearance rates were 2.65% for goalkeepers, 6.47% for defenders,
7.98% for midfielders, and 5.15% for forwards.

The opening-squad objective gives every starter their full projection. Bench
players receive only their risk-adjusted projection multiplied by the 17%
autosub activation estimate. Full bench points are never counted outside Bench
Boost.

## Robustness tournament

The live 2026/27 player pool was re-optimized over 27 deterministic scenarios:

- autosub activation: 12%, 17%, and 24%;
- 2026/27 BPS adjustment magnitude: 75%, 100%, and 125%;
- team-change/DC-role adjustment magnitude: 60%, 100%, and 140%.

The tournament produced seven distinct legal squads. The central balanced
squad was also the most common squad, but appeared in only 8 of 27 scenarios
(29.63%). It is therefore the current recommendation, not a universally robust
optimum.

### Player stability

Locked in all 27 scenarios:

- Bart Verbruggen
- Bruno Fernandes
- Dominic Calvert-Lewin
- Dominik Szoboszlai
- Erling Haaland
- Luke Shaw
- Ollie Watkins
- Senne Lammens
- Tyrick Mitchell

Stable:

- Ethan Ampadu: 24/27
- Issa Diop: 24/27
- Virgil van Dijk: 20/27
- James Tarkowski: 19/27

Fragile:

- Will Hughes: 18/27
- Elliot Anderson: 16/27

Anderson's label is especially important: his previous-season defensive work
is retained as evidence, but the model separately applies the 2026/27 BPS
regime adjustment and a capped team/role-transition penalty. Those penalties
are auditable rather than silently blended into his projection.

## Serving and audit behavior

- The API serves robustness labels only when the report and current bootstrap
  hashes match.
- The API exposes `p10-gw1-calibrated-robustness-v1` as the decision-engine
  version.
- Immutable GW1 shadow snapshots include the decision-engine version, opening
  policy version, and robustness summary in their decision hash.
- A rules, player-pool, projection, or calibration change therefore produces a
  detectable audit change.
- The report is written to
  `data/processed/p10_calibration_report.json`.

## Interpretation

P10 supports a balanced, playable bench because historical autosubs are common,
while correctly discounting bench points outside Bench Boost. It also prevents
the application from presenting every selected player with equal confidence.
Fragile positions should be revisited after final preseason lineups and deadline
team news rather than treated as locked decisions.
