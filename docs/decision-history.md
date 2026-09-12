# SquadMetric decision history

This is the consolidated record of the implementation phases and experiments that
preceded the current product. It replaces the old root-level `phase-*.md`, roadmap,
audit, and handoff files. Git history remains the source for commit-level detail.

## Current production contract

- Product: recommendation-only Fantasy Premier League decision support. It never
  signs in to FPL or executes transfers, captaincy, lineup, or chip actions.
- Active portfolio: `r2_validated` (`r2-consumer-portfolio-v1`). Ridge Regression
  serves transfers, captaincy, and lineup selection; Gradient Boosting serves chip
  valuation. `m8_control` is the all-Ridge rollback.
- Opening squad: `horizon_8_flexible_cold_start_safe`. It uses an identity-safe
  eight-Gameweek policy when prior seasons exist and a value baseline otherwise.
- In-season engine: deterministic beam search over legal transfer, lineup,
  captaincy, and bench states. The live route honors the requested three-, five-,
  or eight-Gameweek horizon and evaluates multi-transfer bundles against the
  manager's reconstructed free-transfer balance.
- Rules: season-versioned scoring, BPS, defensive contributions, transfers,
  selling prices, and chip inventories. Current 2026/27 rules use eight chips in
  two half-season sets, a GW19 reset, DC v1, and BPS v2.
- Data safety: historical decisions are point-in-time safe; unavailable defensive
  contribution data remains missing; scoring eras are never blended.
- Evidence: recommendations can be frozen before a deadline and settled only after
  official FPL marks the Gameweek both finished and data-checked.
- Live rolling form: finalized current-season rows are joined by stable FPL element
  ID. Serving fails closed if an official finalized Gameweek is absent from the
  model bundle.
- Manager economics: free transfers and purchase/selling prices are reconstructed
  from public transfer history; incomplete price evidence suppresses advice.
- Chip policy: proactive chip calls are disabled by default until a credible
  season-long owned-squad validation record exists.
- Actionability: marginal transfers are shown as alternatives rather than calls;
  the production threshold scales from three points at a three-Gameweek horizon
  to eight points at an eight-Gameweek horizon, before any hit cost.

## Accepted engineering and decision changes

### Rules, fixtures, chips, and legal state

- Added immutable fixture scenarios and hashes for three-, five-, and
  eight-Gameweek horizons, including blanks, doubles, postponements, and
  rescheduling uncertainty.
- Implemented season-specific Wildcard, Free Hit, Bench Boost, Triple Captain,
  and historical 2024/25 Assistant Manager rules. Assistant Manager is not exposed
  for the current season.
- Corrected Free Hit reversion and Wildcard permanence for squad, bank, free
  transfers, and player cost bases.
- Repaired chip save-value evaluation so a chip is compared with saving that exact
  slot for a later legal window. This also made squad-changing chip gains auditable.
- Promoted the deterministic beam planner as the shared legal engine after runtime,
  cache-key, horizon, counterfactual, and API-alignment repairs.

### Identity, opening squad, and availability

- Removed the invalid assumption that FPL element IDs identify the same player
  across seasons. Prior evidence is matched only through unambiguous identity-safe
  logic; unmatched players retain uncertainty.
- Promoted the cold-start-safe eight-Gameweek opener. Against its identity-safe
  control it recorded deltas of 0, +198, and +12 across 2023/24, 2024/25, and
  2025/26: +210 aggregate with no seasonal regression under that frozen simulator.
- Added conservative priors for new players and promoted teams, plus official
  availability caps for injuries, suspensions, and unavailable players.
- Added maximum-points, balanced, and safer-depth opening profiles. Balanced is the
  default; the other profiles remain optional review views.

### Scoring, autosubs, prices, and roles

- Corrected 2026/27 interpretation: defensive-contribution thresholds remain 10
  CBIT for defenders and 12 CBIRT for midfielders/forwards; the material change is
  reduced BPS overlap for CBI actions.
- Calibrated bench value from historical autosub activation instead of counting
  full bench points outside Bench Boost.
- Added transition-aware official penalty, direct-free-kick, and corner roles.
  Only the change from the prior official role is added, preventing double counting
  of historical goals, assists, xG, and xA.
- Corrected FPL economics by separating purchase, current, and selling prices.
  Price rises now realize half-profit in £0.1m steps; falls are realized fully.
  Wildcard and Free Hit budgets use selling value plus bank.

### Production routing and live operation

- Separated projections by consumer, then promoted Ridge for transfers and
  captaincy. Gradient Boosting chip valuation remains available only behind an
  explicit experimental flag. Added explicit metadata and an all-Ridge rollback.
- Built the complete planner response: transfers/roll, hits, chip slot, XI, ordered
  bench, captain, vice, immediate/horizon value, uncertainty, opportunity cost,
  provenance, and legal alternatives.
- Added live official-data overlays so ordinary price, availability, role, fixture,
  and player-pool movement does not unnecessarily block the website. Rules drift,
  team-count drift, corrupt artifacts, hash failures, and model-load failures still
  fail closed.
- Added immutable deadline evidence and idempotent post-Gameweek learning. Current
  season rows are appended only after official finalization and retain the original
  pre-deadline market snapshot.
- Added Supabase authentication and owner-isolated account tables protected by Row
  Level Security.

## Historical results and their limits

The identity-safe opening repair changed its frozen three-season total from 6,441
to 6,651. The later same-chip save-value repair changed its frozen scorecard from
2,321 / 2,194 / 2,136 to 2,321 / 2,360 / 2,249, or 6,930 total. Direct Free Hit
gains in that audit were +10, +3, +28, and +64 rather than zero.

Those totals are not a definitive current-code baseline. The selling-price repair
was applied after several tournaments and removed impossible purchasing power. In
simpler deterministic-transfer controls it reduced realistic totals by 55 points
in 2023/24 and 67 in 2024/25 while leaving no-transfer controls unchanged. A fresh
three-season production/control/no-chip replay on current code is required before
publishing a definitive performance claim.

Historical top-1% boundaries are evaluation references only. They never enter a
deadline decision and cannot guarantee a future rank.

## Consumer tournament ledger

The final consumer tournament changed one assignment at a time against the frozen
champion:

| Candidate | 2023/24 | 2024/25 | 2025/26 | Aggregate | Decision |
|---|---:|---:|---:|---:|---|
| Ridge chip model | +11 | +126 | -38 | +99 | Validated challenger; not promoted because it regressed in the latest eight-chip regime |
| Gradient transfer model | -113 | +176 | -156 | -93 | Rejected |
| Gradient lineup model | -1 | +12 | -26 | -15 | Rejected |
| Horizon-value hit policy | -103 | -222 | -41 | -366 | Rejected and confounded by narrower beam breadth |

## Production, provisional, and rejected boundaries

Accepted production behavior includes versioned rules, stable identities, current
availability/role priors, the eight-Gameweek cold-start-safe opener, correct FPL
economics, chip state and reversion, same-chip opportunity cost, `r2_validated`
routing, deterministic legal planning, set-piece transitions, recommendation-only
UI, account RLS, deadline evidence, and finalized-only learning.

Provisional or evidence-only behavior includes the Ridge chip challenger,
rank-relative review, maximum-points and safer-depth opening profiles, three- and
five-Gameweek openers, all-Ridge shadow comparison, and component/team/minutes-band
forecasts unless independently promoted.

Rejected behavior must remain unreachable from defaults:

- failed M2/M9 minutes variants;
- M5 narrow transfer lookahead;
- M7 component and M10 team-component production replacements;
- Gradient transfer and lineup routing;
- the confounded horizon-value hit policy;
- the cross-season element-ID opener;
- the retired Streamlit UI and standalone captaincy/lineup experiment runners;
- the Random Forest artifact;
- current-season Assistant Manager.

## Known limitations and next evidence gate

- `max_same_gameweek_transfers=1` means the normal planner does not meaningfully
  explore most deliberate two-transfer `-4` plans. A future hit experiment must
  hold candidate breadth constant and change only the hit decision.
- Exact raw bootstrap hashes can move between sequential operational reports due to
  volatile official selection-rank and price-projection fields. Decision evidence
  remains tied to one frozen serving snapshot.
- Production deployment still requires a persistent FastAPI host, configured
  Next.js origin, Supabase production callbacks, service-role account deletion,
  OAuth, SMTP, TLS, monitoring, and end-to-end verification.
- The next modeling intervention should follow real frozen deadline evidence and
  change one consumer or policy at a time. Do not begin another broad model
  tournament before the corrected-economics baseline and live evidence loop are
  trustworthy.
