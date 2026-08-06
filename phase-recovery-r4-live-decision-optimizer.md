# Recovery R4 — Live Decision Optimizer

## Status

Implemented and regression-tested. The live planner now returns a complete
decision recommendation using the validated R2 portfolio and the same legal
beam engine used by the chip-aware benchmark.

## Delivered

The `/api/predictions/planner` response now includes:

- ordinary transfer or roll decision;
- transfer hit cost and hit selection;
- chip and chip slot when selected;
- legal starting XI;
- bench order;
- captain and vice-captain;
- expected Gameweek points;
- expected horizon points and no-chip comparison;
- uncertainty penalty and decision reason;
- active portfolio and consumer model metadata.

The optimizer uses:

- current squad, bank, and free-transfer state;
- live chip inventory and season-specific rules;
- transfer legality and budget constraints;
- Blank and Double Gameweek projections;
- separate transfer and chip projection frames;
- the deterministic beam planner;
- the R3 shadow comparison when enabled.

The response retains the previous projection baseline and player pool, so the
new decision object is additive and does not remove existing UI data.

## Safety behavior

- Incomplete squads receive `decision: null` with an explicit error.
- Missing decision-gameweek projections do not fabricate a recommendation.
- Planner errors do not produce automatic actions.
- Shadow comparison remains non-invasive.
- R2 portfolio and M8 control rollback remain explicit.

## Validation

- Complete decision payload synthetic test added.
- Existing planner API tests updated for the team-history dependency.
- Focused R4/API tests pass.
- Full regression suite after R4: `165 passed`.
- Ruff: clean.

## Acceptance decision

R4 passes its engineering gate. The endpoint is a recommendation surface
only: it never submits transfers or chips to FPL.
