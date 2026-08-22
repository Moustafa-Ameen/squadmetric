# P11 — GW1 Deadline Finalization

## Status

The deadline pipeline is implemented and operational as of 10 August 2026.
The recommendation is deliberately `monitoring`, not final: the GW1 deadline is
21 August 2026 at 18:30 BST and the final 24-hour news window has not opened.

P11 does not automatically submit a squad to FPL.

> Update: P12 subsequently added explicit set-piece transition intelligence
> and reran P10/P11 against a newer 10 August bootstrap. The current squad and
> robustness result are recorded in `phase-p12-set-piece-intelligence.md`; the
> figures below remain the pre-P12 P11 checkpoint.

## Official refresh

The 10 August official FPL refresh produced:

- 573 players;
- 20 teams;
- 380 fixtures;
- eight chips with the GW19 half-season reset;
- `dc_v1` defensive-contribution rules;
- `bps_v2_2026_27` bonus rules;
- no artifact errors or warnings;
- bootstrap hash
  `7a26d18ef14d4df1e54a4a7532853cf7011f1627c6638a1439d03619a7642a5e`.

There were 15 material availability/news changes since 7 August, but none
affected a selected player. Every current selection remains officially marked
available. Prices remain locked until the GW1 deadline.

The official preseason guidance specifically warns managers to monitor final
preseason lineups and late World Cup returns rather than assuming early
friendly involvement proves a GW1 start:

- <https://www.premierleague.com/en/news/4679613/what-to-look-out-for-in-pre-season-ahead-of-202627-fantasy>
- <https://www.premierleague.com/en/news/4680462/whats-new-in-202627-fantasy-price-change-predictor>

## Refreshed robustness result

The complete P10 tournament was rerun against the new bootstrap hash.

| Measure | 7 August | 10 August |
| --- | ---: | ---: |
| Scenarios | 27 | 27 |
| Distinct legal squads | 7 | 4 |
| Central-squad frequency | 8 | 12 |
| Central-squad rate | 29.63% | 44.44% |

The central recommendation, formation, captain and vice-captain did not change.
Expected GW1 points moved from 60.26 to 60.23.

Current recommendation:

- formation: 3-4-3;
- cost: £100.0m;
- captain: Erling Haaland;
- vice-captain: Bruno Fernandes;
- bench order: Tyrick Mitchell, Issa Diop, Will Hughes, Bart Verbruggen.

## Fragile-slot challenge

P11 evaluates complete legal squad variants rather than presenting isolated
one-for-one swaps.

The central squad is supported by 12/27 scenarios. The primary challenger is
supported by 7/27 scenarios and makes a joint midfield change:

```text
OUT: Will Hughes + Elliot Anderson
IN:  Enzo Le Fée + Noah Sadiki
```

Other scenario-supported alternatives require wider goalkeeper or defensive
restructuring. They are persisted in
`data/processed/p11_deadline_finalization.json`.

Anderson remains fragile at 17/27 scenarios. Hughes remains fragile at 15/27.
The official FPL analysis also identifies genuine uncertainty around whether
Anderson retains his defensive-contribution and set-piece value after moving
to Manchester City:

- <https://www.premierleague.com/en/news/4677216/fpl-signings-will-andersons-defensive-contributions-be-reduced-at-man-city>

The current evidence therefore supports retaining the central squad today,
while monitoring the two-player challenger through the final friendlies and
team-news window.

## Fail-closed deadline gate

The recommendation can become `finalization_ready` only when:

- current artifacts are no more than 24 hours old;
- P10 and the serving manifest have the same bootstrap hash;
- the balanced central squad matches the scenario mode;
- all 15 selected players remain available;
- the official deadline exists;
- the final 24-hour window has opened;
- final team news has been manually reviewed with at least one official source
  URL.

The planner displays the monitoring/finalization state and primary challenger.
The operations checklist no longer treats old shadows as current or marks final
team news as passed merely because the deadline is far away.

## Refresh and audit behavior

The daily refresh now runs, in order:

1. official artifact refresh;
2. P10 27-scenario robustness rebuild;
3. P11 deadline gate and challenger report;
4. immutable GW1 shadow capture.

The latest 10 August shadow uses schema `p11-gw1-shadow-v3` and decision hash
`11009e86a13ad7867fd01f306d3f941ba0f1a13f1c3053d02c22cf889d75cc9e`.
No player, captain or vice-captain changed from 7 August; the bootstrap changed
and expected GW1 points decreased by 0.03.
