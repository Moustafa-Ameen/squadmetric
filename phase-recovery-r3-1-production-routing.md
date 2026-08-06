# Recovery R3.1 — Production Portfolio Routing

## Objective

Wire the validated R2 consumer portfolio into the live application without
silently changing the benchmark control or enabling failed experimental
variants.

## Current defect

The historical R2 challenger validated:

- Ridge Regression for ordinary transfers;
- Ridge Regression for captaincy;
- Gradient Boosting Regressor for chip valuation.

The live API currently uses the Gradient artifact for the general planner and
the transfer prediction endpoint. The chip endpoint does not identify the
projection portfolio that produced its recommendation. This means the live
application is not using the same consumer routing that passed R2.

## R3.1 implementation

- Add one central production-portfolio configuration.
- Make the validated R2 portfolio the default:
  `Ridge transfer + Ridge captain + Gradient chip`.
- Keep an explicit `m8_control` rollback portfolio:
  `Ridge transfer + Ridge captain + Ridge chip`.
- Select the portfolio through a validated environment setting rather than
  scattered constants.
- Route the transfer endpoint and general planner through the active transfer
  model artifact.
- Route chip projections through the active chip model artifact.
- Return portfolio version and consumer model names in API metadata.
- Preserve the existing no-team, preseason, and missing-artifact responses.

## R3.1 tests

- Default portfolio is the validated R2 assignment.
- Rollback portfolio is deterministic and uses Ridge for every consumer.
- Invalid portfolio settings fail safely.
- Transfer endpoint reports the active transfer model.
- General planner reports the active transfer model and portfolio version.
- Chip recommendations report the active chip model and portfolio version.
- Model artifact selection is consumer-specific.
- Existing API and chip legality tests remain unchanged.

## R3.1 acceptance gate

R3.1 passes only if:

- No failed M2/M5/M9/M10 variant is routed by default.
- The live transfer/planner path uses Ridge by default.
- The live chip path uses Gradient by default.
- The rollback path can be selected deterministically.
- API responses identify the active portfolio and model assignments.
- Full tests and Ruff pass.

R3 is now complete: shadow-mode comparison, persisted live decision audits,
operational status, and rollback reporting were added after this routing
contract. No automatic transfer or chip execution is introduced.
