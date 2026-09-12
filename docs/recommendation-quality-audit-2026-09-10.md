# SquadMetric recommendation quality audit

## Executive summary

**Assessment at audit start: recommendation output needed revision before it could
be trusted for live transfers or chips.** The software was mechanically healthy—the
repository was clean, all 305 Python tests passed locally, Ruff passed, and the
latest GitHub Actions run was green—but recommendation quality was being undermined
by incorrect and incomplete live state. The remediation and current verification
status are recorded below.

The largest defect is in the serving path. The live projector asks
`data_service.historical_player_gw()` for rolling form, which loads only
`historical_player_gw.csv`. That file ends in 2025/26. The current-season
`live_2026_27_player_gw.csv` is added to model training, but it is not supplied to
the live rolling-feature builder. As a result, the 2026/27 planner is deriving
`minutes_last_3` and `points_last_3` from the latest available prior-season
player rows. A safe isolated refresh through GW3 retrained the models but did not
change this serving path or remove the bad Wissa-to-Calvert-Lewin recommendation.

The current GW4 output illustrates the effect. Official FPL data shows Yoane Wissa
has started all three matches, played 261 minutes, scored 13 points, and has
4.3 expected points for GW4. Dominic Calvert-Lewin has also started all three,
played 252 minutes, scored 10 points, and has 3.3 expected points. SquadMetric
instead gives Wissa a 43.3% start probability and 1.84 projected points, versus
Calvert-Lewin at 85.4% and 4.35, then recommends the transfer for a 2.51-point
immediate gain.

The second critical issue is manager state. The public entry response does not
provide exact free transfers, purchase prices, or selling prices. The engine
silently assumes one free transfer, the API displays zero, and missing sale values
fall back to current market price. On the separately linked personal test team,
no ordinary transfers were made
in GW1 or GW2 and the GW3 Wildcard retains saved free transfers under the official
rules, so the correct GW4 state is two free transfers—not zero or one. The engine
also accepts a requested horizon of eight but always searches three Gameweeks and
allows only one same-Gameweek transfer.

The immediate next action is a narrow **state-integrity repair**, not another broad
model tournament:

1. Fail closed when current-season rolling inputs, exact free transfers, or
   purchase/selling prices are unknown.
2. Feed finalized current-season player rows into the live rolling features using
   stable current-season IDs, with explicit fallback behavior for new players.
3. Make the selected horizon the actual optimization horizon and allow transfer
   bundles up to the manager's real free-transfer count.
4. Disable proactive chip recommendations until chip opportunity cost is measured
   over a credible season window.
5. Add a persistent model-managed shadow team and grade every frozen deadline
   decision against legal alternatives.

Manual refresh can remain manual, as requested. It must become a hard readiness
gate: stale artifacts should produce “recommendations unavailable,” not a confident
transfer.

## Remediation completed on 11 September 2026

The state-integrity repair is now implemented and exercised against live official
data:

- serving combines historical training rows with finalized current-season rows;
- rolling form resolves by stable current-season element ID before name fallback;
- readiness blocks when any official finalized Gameweek is absent from model
  metadata, while live prices, availability, roles, fixtures, and ownership are
  still applied on every request;
- manual refresh ingested GW3, bringing the live table to 1,835 rows and model
  training to 87,146 rows across 2023/24–2026/27;
- free transfers are reconstructed from public transfer/chip history and purchase
  and selling prices from transfer costs plus the immutable GW1 price snapshot;
- transfers already made for the upcoming Gameweek are applied to the prior-deadline
  squad, remaining free transfers, and current bank before generating another plan;
- three-, five-, and eight-Gameweek requests now execute those actual search
  horizons, with multi-transfer plans allowed from the real free-transfer state;
- proactive chip calls are off by default pending season-long owned-squad evidence;
- transfers must clear a horizon-scaled actionability threshold plus any hit cost;
- the home dashboard consumes the personalized decision center rather than calling
  generic rankings “your” recommendation or hard-coding high confidence;
- post-GW1 refresh no longer regenerates opening-squad calibration/finalization
  artifacts, and shadow capture rejects post-deadline reconstruction;
- an explicitly identified model-team scorecard now excludes personal-team results
  by contract and compares each finalized Gameweek with the official average;
- frontend dependencies were patched from Next.js 16.3.1 to 16.3.4 and related
  vulnerable packages; the production dependency audit reports zero findings.

The corrected GW4 diagnostic no longer recommends Wissa to Calvert-Lewin. Wissa is
now estimated at 96.7% to start and 4.20 points, versus Calvert-Lewin at 93.3% and
4.02. The public-history reconstruction reports two free transfers. At three and
eight Gameweeks, the transfer safety policy recommends rolling and saving chips
instead of presenting the earlier marginal move as actionable advice.

The row-level xG/xA challenger was also rerun in memory. It improved every trained
model's held-out MAE (for example Gradient Boosting from 1.010 to 1.003 and Ridge
from 1.060 to 1.045), but it is not promoted here: row-level MAE is insufficient
evidence that the legal owned-squad strategy improves in every validation season.
That richer feature set remains a challenger until the decision-level replay passes.

## What is actually working

| Area | Audit result |
|---|---|
| Repository | Clean `main`, synchronized with `origin/main` at audit start |
| Python verification | 317 tests pass after remediation; 305 passed at audit start |
| Static analysis | Ruff passed |
| GitHub Actions | Latest run for the current HEAD passed |
| Rules/legal mechanics | Strong test coverage around squad legality, chips, prices, autosubs, and evidence |

### Evidence boundary: the 220-point team is not SquadMetric

Team 3254925 ("bestest team") is the owner's personal team. Its 220 points and
rank are unrelated to SquadMetric's model-managed squad and must not be used as
product-performance evidence. It appears in this audit only because its public
history exposed the free-transfer and price-state defects in a reproducible live
request.

The model-managed squad reportedly scored below the overall average in every
completed Gameweek. The repository no longer contains an immutable original GW1
model-squad snapshot: a post-deadline refresh overwrote the opening-squad report.
Therefore this audit does not state or reconstruct a model score from later data.
That missing evidence is itself an operational defect addressed by the immutable
shadow-team recommendation below.

## Root-cause findings

### 1. Critical: live form is sourced from the wrong season

The production feature list is intentionally small:

- price before deadline;
- minutes over the last three;
- points over the last three;
- a single opponent-strength value;
- ownership and market-snapshot availability;
- position and home/away.

The live route builds current player metadata, then calls `project_players` with
`history=data_service.historical_player_gw()` in
`api/live_projection_service.py:224-234`. The data service maps that name to
`data/processed/historical_player_gw.csv` in `api/data_service.py:51,124-125`.
That file contains 85,311 rows across 2023/24–2025/26 and no 2026/27 rows.

The rolling builder then selects the maximum season and takes the last three rows
per normalized player name in
`src/fpl_intelligence/multi_gw_projection.py:498-530`. It therefore treats
2025/26 as “current” during 2026/27. The separate live history contains 1,206
finalized 2026/27 rows for GW1–GW2, but the serving call never combines it with the
historical frame.

The safe refresh experiment copied the repository outside the workspace, ingested
finalized GW3, and retrained on 87,146 rows including GW1–GW3. The recommendation
still remained Wissa to Calvert-Lewin, with Wissa's start probability only moving
from 43.3% to 43.9%. That isolates the failure to live feature construction rather
than refresh age alone.

### 2. Critical: manager state is silently fabricated

The planner uses:

- `int(team_entry.get("free_transfers") or 1)` for the engine
  (`api/routers/planner.py:218`);
- `int(team_entry.get("free_transfers") or 0)` for the response
  (`api/routers/planner.py:312`).

The same request therefore plans with one free transfer while displaying zero.
The public picks payload also does not contain purchase or selling prices. In
`api/chip_recommendations.py:130-144`, missing values fall back to current price,
which can overstate spendable value after price rises because FPL realizes only
half the profit in £0.1m steps.

For the personal diagnostic team 3254925, the official history shows zero ordinary transfers before GW2
and GW3. That means two saved transfers entering the GW3 Wildcard. Official rules
state that saved free transfers are retained after playing a Wildcard, making the
inferred GW4 balance two. The live optimizer should reconstruct this state from
public transfer/chip history, expose its provenance, and abstain when exact
purchase-price evidence is incomplete.

### 3. High: “8 Gameweeks” is really a three-Gameweek search

The route calculates projection frames for the requested horizon but constructs
`DeterministicBeamPlanner(horizon=min(3, projection_horizon))` in
`api/routers/planner.py:213`. Because supported planner requests project at least
eight Gameweeks internally, the decision search is always capped at three.

The planner default also sets `max_same_gameweek_transfers=1` in
`src/fpl_intelligence/beam_search.py:108-126`. It cannot properly compare a
two-transfer plan even when the manager has banked two or more free transfers.
This makes the UI control misleading and biases decisions toward shallow,
one-player moves.

### 4. High: chips are priced with a short and weak opportunity-cost window

The frozen GW2 and GW3 evidence for the separately linked personal manager selected
Triple Captain in both weeks because the manager did not follow the first
recommendation and the second recommendation was generated from that manager's
actual chip state. GW3's stored opportunity cost for
using Triple Captain was only 0.56 points. That may be locally consistent with a
three-Gameweek search, but it is not credible season-long chip valuation.

Frozen immediate outcomes were superficially good:

| Frozen deadline | Selected action | Actual selected score | Best frozen branch | Immediate regret |
|---|---|---:|---:|---:|
| GW2 | Triple Captain; Vušković → Shaw | 113 | 115 | 2 |
| GW3 | Triple Captain; Calafiori → Guéhi | 65 | 65 | 0 |

These are only two personal-team deadline states, not independent seasons, and do
not represent a persistent model-managed squad. They show that the legal counterfactual machinery
works; they do not validate long-run chip strategy.

### 5. High: the model's signal is modest and the evaluation target is misaligned

Completed-season reference metrics show:

| Model | Adjusted MAE | Precision@10 |
|---|---:|---:|
| Gradient Boosting | 0.918 | 12.7% |
| Random Forest | 0.924 | 10.8% |
| Ridge | 0.935 | 11.1% |
| Naive baseline | 1.017 | 8.1% |

The adjusted Gradient model improves MAE by about 9.7% over the naive baseline,
but top-10 precision remains 12.7%. More importantly, MAE over every player-row is
not the product decision: users need correct rankings among viable, affordable,
owned-or-buyable players.

The captaincy backtest is also optimistic. It chooses the highest predicted player
from the entire player pool each Gameweek
(`src/fpl_intelligence/step7_evaluation.py:131-147`), not the best captain from a
legal owned squad. The report itself acknowledges “no real FPL squad constraints”
at lines 236-238. Its 468-point Ridge captain total is therefore not evidence that
the live captain recommendation works.

The three-season strategy totals in `docs/decision-history.md` are likewise not a
current production baseline: that document explicitly says the selling-price fix
landed after several tournaments and that a fresh replay is still required.

### 6. Medium: tests protect mechanics more than recommendation truth

The local suite and green CI are meaningful engineering positives, but
passing tests cannot catch a bad football prior unless the expected state is
asserted. Existing API tests monkeypatch `historical_player_gw`; there is no
regression test proving that finalized 2026/27 rows drive the live
`minutes_last_3` and `points_last_3` features. CI also excludes tests marked
`requires_local_artifacts`, while model and processed-data artifacts are ignored
by Git.

This creates a deployment/reproducibility risk: a green commit does not by itself
prove that the server has the same model/data bundle that produced the audited
recommendation.

## Fantasy Football Hub comparison

Fantasy Football Hub's exact optimization algorithm and claimed accuracy are
proprietary, so this audit does not pretend to reproduce or verify them. The public
product surface does establish a materially richer decision context:

| Decision input | SquadMetric now | FFH public product surface |
|---|---|---|
| Current form | Three rolling points/minutes fields, currently wrong-season in serving | Form versus expected points over recent GWs |
| Chance quality | xG/xA feature modes exist but are not used in the live trained portfolio | Opta shots, big chances, key passes, and positional ranks |
| Minutes/role | Historical minutes classifier plus live availability status | Explicit expected minutes plus predicted lineups and team news |
| Fixture context | One opponent-strength scalar and home/away | Six-fixture views, difficulty, predicted points, filters |
| Team planning | Legal beam search, but three GWs and one simultaneous transfer | Separate team rating, AI transfers, AI teams, and planning tools |
| Transparency | Inspectable code and frozen counterfactual evidence | Proprietary recommendations; public feature surface only |

FFH's public player profiles explicitly combine form versus expectation, Opta
underlying metrics, defensive contributions, the next six fixtures, predicted
points, and expected minutes. Its Opta table supports player/team, per-start,
per-90, home/away, Gameweek, and fixture filters. Its tools catalog also separates
team optimization, player predictions, fixture analysis, price changes, player
comparison, predicted lineups/team news, set pieces, and expert views.

The lesson is not “copy FFH.” It is to separate and validate the layers:
current-role/minutes, chance quality, team/opponent strength, price/state
economics, and legal multi-week optimization. SquadMetric currently has a strong
legal shell around a thin and sometimes stale projection core.

## Recommended action

### Immediate repair — before showing another live recommendation

Implement one state-integrity vertical slice:

1. Build a single point-in-time serving frame that joins finalized 2026/27 history
   to current FPL players by current-season element ID.
2. Assert the source season and latest finalized GW for every rolling feature.
3. Require exact manager free transfers and price bases, or return a clearly
   non-actionable “state incomplete” response.
4. Honor the requested three-, five-, or eight-Gameweek search horizon.
5. Permit no-hit transfer bundles up to the true free-transfer balance.
6. Put chip advice behind an explicit experimental flag.
7. Add tests that fail if current-season rows are absent, stale, or replaced by
   prior-season rows.

Acceptance should include a fixture-level trace showing why each of Wissa and
Calvert-Lewin received its minutes probability and projected points. The repair is
successful when a refresh changes live rolling inputs, manager state is internally
consistent, and the planner can explain a recommendation without hidden fallbacks.

### Projection quality — after state integrity is trustworthy

Add richer, point-in-time-safe inputs one group at a time:

- player xG, xA, shots, big chances, key passes, and penalty-area involvement;
- separate team attack and defense strength, adjusted for opponent and venue;
- explicit expected-minutes and predicted-lineup/news features;
- defensive-contribution likelihood by position;
- uncertainty intervals and downside-aware transfer thresholds.

Each challenger should be evaluated on legal-squad transfer regret, captain regret,
chip opportunity cost, and season total—not only player-row MAE.

### Evidence — establish a record that can earn trust

Run a persistent shadow team from an immutable GW1 state. Freeze every deadline
decision without future information, carry the model's own transfers/chips/state
forward, settle after official finalization, and publish:

- model score versus no-transfer and simple-template baselines;
- transfer and captain regret;
- chip value versus save-to-later counterfactuals;
- calibration by projected-points and expected-minutes bands;
- stale/unknown-state abstention rate.

Do not make a performance claim until that replay uses the current economics,
current rules, current feature pipeline, and legal owned-squad captaincy.

## Validation and caveats

**Overall assessment: ready to share as a diagnostic; the recommendations
themselves need revision.**

Highest-impact figures were reconciled against official live FPL entry, history,
bootstrap, and player data on 10 September 2026 (Asia/Dubai). The current GW4 API
response was reproduced against the untouched workspace. A separate temporary
copy was refreshed through finalized GW3 to isolate freshness from serving logic.
The repository remained unchanged during those experiments.

Caveats:

- Only GW1–GW3 of the 2026/27 season have been completed, so live outcome evidence
  is necessarily small.
- The 220-point personal team and two frozen personal-team recommendation scores
  are not SquadMetric model-team results.
- The original model-managed GW1 squad cannot be graded exactly from the current
  repository because its immutable snapshot was not retained.
- FFH's public pages verify its exposed inputs and tools, not the internals or
  accuracy of its proprietary algorithm.
- Free-transfer state is inferred deterministically from official public transfer
  and chip history and must be labeled with that provenance.

## Sources

- Personal diagnostic FPL entry (not the model team): <https://fantasy.premierleague.com/api/entry/3254925/>
- Personal diagnostic FPL history (not the model team): <https://fantasy.premierleague.com/api/entry/3254925/history/>
- Official FPL bootstrap/player data: <https://fantasy.premierleague.com/api/bootstrap-static/>
- Official FPL rules: <https://fantasy.premierleague.com/help/rules>
- FFH player profiles: <https://www.fantasyfootballhub.co.uk/player-profile>
- FFH Opta statistics: <https://www.fantasyfootballhub.co.uk/opta?via=fplmate>
- FFH tools: <https://www.fantasyfootballhub.co.uk/tools/>
- Local model metrics: `data/reference/model_evaluation/`
- Local production contract and historical caveats: `docs/decision-history.md`
- Local artifact freshness: `data/processed/current_artifact_manifest.json`
