# P12 — Set-Piece and Penalty Intelligence

## Status

Implemented and quality-gated on 10 August 2026. P12 makes official penalty,
direct-free-kick, and corner/indirect-free-kick roles explicit in the live
projection and opening-squad pipeline.

P12 is transition-aware. The accepted projection model already contains prior
goals, assists, xG, and historical FPL points, so adding the full estimated
value of every current penalty role would double count established takers.
Instead, P12 applies only:

```text
current official role share - official 2025/26 role share
```

The player's start probability is then applied exactly once by the fixture
projection engine.

## Official role contract

The official bootstrap fields are retained in the normalized player table:

- stable player code;
- `penalties_order` and `penalties_text`;
- `direct_freekicks_order` and `direct_freekicks_text`;
- `corners_and_indirect_freekicks_order` and the associated text.

The raw order values are sorted within each team and category before they are
treated as ranks. A raw value of five can therefore still be a team's first
listed player when no lower value exists for that team.

The role source is the official FPL Scout set-piece table, which states that
its lists use prior matches, preseason evidence, and known player roles and
are updated through the season:

- <https://fplchallenge.premierleague.com/the-scout/set-piece-takers>
- <https://www.premierleague.com/en/news/4675553/why-fernandes-and-haaland-look-like-must-haves-to-start-202627-fpl>

## Missing and uncertain evidence

- Missing set-piece fields remain missing; they are never converted to zero in
  normalized data.
- Promoted-team players without a comparable 2025/26 Premier League team
  baseline receive no transition adjustment. Their current role is still
  shown, but it is not assigned invented historical evidence.
- Competing takers' current availability changes the conditional role share.
- The explicit event-rate and conversion assumptions are persisted in the P12
  report and stressed at 60%, 100%, and 140% in the P10 tournament.
- External reports may explain uncertainty, but do not silently override the
  official bootstrap hierarchy.

## Current audit

The 10 August refresh uses bootstrap hash
`7d38825470d4c077c410568d567b4148d8103e14eef1436e6334ea76cd0b83cf`.
It records current roles for 55 penalty candidates, 52 direct-free-kick
candidates, and 71 corner/indirect-free-kick candidates.

The selected squad contains three official first-listed penalty takers:

- Bruno Fernandes;
- Erling Haaland;
- Dominic Calvert-Lewin.

Selected transition adjustments remain deliberately small. The largest are
Dominik Szoboszlai at +0.094 expected points per start, Luke Shaw at +0.061,
and Bruno Fernandes at −0.039. Elliot Anderson is only +0.008 from his current
corner listing; his previous Nottingham Forest set-piece value is not simply
carried into Manchester City unchanged. This aligns with the official warning
that his new role is uncertain:

- <https://www.premierleague.com/en/news/4677216/fpl-signings-will-andersons-defensive-contributions-be-reduced-at-man-city>

## Re-optimized recommendation

The complete 27-scenario P10 tournament and P11 deadline report were rerun.
The current balanced squad changed from the pre-P12 snapshot:

```text
OUT: Virgil van Dijk + Ethan Ampadu
IN:  Marc Guéhi + Enzo Le Fée
```

Expected GW1 points increased from 60.23 to 61.07. Because an official
bootstrap refresh occurred at the same time, this is the combined refreshed
pipeline result and is not claimed as 0.84 points caused solely by set pieces.

The squad is now the most common result in 6/27 scenarios (22.22%), with ten
distinct legal squads across the tournament. That is less robust than the
pre-P12 12/27 result. The recommendation therefore remains `monitoring`, and
the higher point estimate is not treated as evidence that uncertainty has
disappeared.

The current XI is:

- Senne Lammens;
- James Tarkowski, Marc Guéhi, Luke Shaw;
- Bruno Fernandes, Dominik Szoboszlai, Elliot Anderson, Enzo Le Fée;
- Erling Haaland, Ollie Watkins, Dominic Calvert-Lewin.

Bench order: Tyrick Mitchell, Issa Diop, Will Hughes, Bart Verbruggen.
Haaland remains captain and Bruno vice-captain.

## Serving and audit behavior

- Every selected player exposes normalized set-piece ranks and the transition
  adjustment in the initial-squad API and planner UI.
- The operations deadline checklist requires a P12 report matching the current
  bootstrap hash.
- The daily refresh rebuilds P10, P11, and P12 before capturing the immutable
  shadow recommendation.
- The latest shadow includes the P12 summary in its decision hash.
- The full report is written to
  `data/processed/p12_set_piece_report.json`, including the exact prior-season
  snapshot filename and SHA-256 used by the transition calculation.

P12 does not guarantee a top-1% finish and does not automatically submit any
FPL action.
