# 2026/27 Launch Readiness — Player Role and Availability Intelligence

## Outcome

The live 2026/27 recommendation path now distinguishes established players,
new players, promoted-team players, and currently unavailable players. New
players no longer receive one flat position prior, while injuries and
suspensions can no longer be overridden by optimistic preseason evidence.

This is a live-decision correctness improvement. It does not claim a historical
points gain because the new-player and preseason observations did not exist at
historical FPL deadlines.

## Official launch context

- Coventry City, Ipswich Town, and Hull City are the promoted clubs.
- Official FPL analysis identifies Bobby Thomas and Charlie Hughes as promoted
  defenders with relevant defensive-action records.
- Official Hull analysis records Oli McBurnie's 18-goal promotion campaign.
- FPL's official preseason guidance warns that late returns, new managers, and
  the final preseason matches materially affect starting roles.

Reviewed sources:

- https://www.premierleague.com/en/news/4673099/the-202627-premier-league-season-officially-starts/
- https://www.premierleague.com/en/news/4680821/the-scouts-analysis-of-15-key-player-prices-in-202627-fantasy
- https://www.premierleague.com/en/news/4664386/all-you-need-to-know-as-hull-city-are-promoted-to-premier-league
- https://www.premierleague.com/en/news/4679613/what-to-look-out-for-in-pre-season-ahead-of-202627-fantasy

## Implementation

- Added a timestamped, cutoff-safe launch-evidence contract.
- Added reviewed 2026/27 evidence for Bobby Thomas, Charlie Hughes, and Oli
  McBurnie. Role probabilities are explicitly model inferences rather than
  claims made by the source.
- Replaced the generic new-player fallback with conservative priors informed by
  position, price, ownership, and promoted-team uncertainty.
- Fixed the preseason-prior merge so canonical columns cannot silently become
  `_x`/`_y` duplicates.
- Fixed minutes security to fall back per player. Previously, the presence of
  historical minutes anywhere in the table caused all zero-minute newcomers to
  lose their valid priors.
- Added availability probabilities derived from official status/chance fields.
  Injury, suspension, and unavailable states hard-cap minutes security.
- Integrated role and availability priors into live multi-Gameweek projections.
- Persisted current bootstrap availability events with event IDs and timestamps.
- Added evidence and availability hashes to the serving artifact manifest.
- Bumped the current artifact schema to
  `current-artifacts-v2-launch-intelligence`; stale v1 bundles now fail closed.
- Aligned the live eight-week opening-squad endpoint with the production
  `horizon_8_flexible_cold_start_safe` policy and version.
- Exposed availability, starting likelihood, evidence provenance, cost, and bank
  in opening-squad responses.

## Current snapshot reconciliation

- Season: 2026/27
- Players: 572
- Teams: 20
- Fixtures: 380
- Availability events: 60
- Historical training rows: 85,311
- Historical training seasons: 2023/24 through 2025/26
- Rules: eight chips, GW19 reset, BPS v2, DC v1
- Readiness errors: 0
- Readiness warnings: 0

Evidence behavior in the refreshed table:

- Bobby Thomas: available; evidence-informed minutes prior retained.
- Oli McBurnie: available; evidence-informed minutes prior retained.
- Charlie Hughes: currently injured; official availability sets minutes
  security to zero despite positive long-term role evidence.

## Real API smoke test

The production endpoint returned HTTP 200 with:

- 15 legal players costing 100.0;
- a 3-4-3 starting formation;
- no injured, suspended, unavailable, or zero-availability player;
- production policy `horizon_8_flexible_cold_start_safe`;
- production version `p3-opening-milp-v2-cold-start-safe`;
- Erling Haaland captain and Bruno Fernandes vice-captain for the current
  snapshot.

Two cheap defenders in the generated bench had low starting likelihood. This is
persisted as a visible launch risk, not treated as proof that the squad is
optimal. It should be reassessed after the final preseason lineups and deadline
news refresh.

## Acceptance boundary

The launch layer is accepted only when focused and full regression tests, Ruff,
frontend checks, artifact readiness, and a real endpoint smoke test pass. Live
recommendations remain point-in-time recommendations, not a top-1% guarantee.
