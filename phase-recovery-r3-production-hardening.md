# Recovery R3 — Production Hardening and Shadow Validation

## Status

Complete and regression-tested. R3 now routes the validated R2 portfolio into
the live API, provides an explicit rollback configuration, and supports
non-invasive shadow comparison against the M8.6.1 Ridge control.

## Active routing

Default portfolio:

```text
transfer: Ridge Regression
captain: Ridge Regression
chip: Gradient Boosting Regressor
```

Rollback portfolio:

```text
transfer: Ridge Regression
captain: Ridge Regression
chip: Ridge Regression
```

Select the rollback before starting the API with:

```text
FPL_PRODUCTION_PORTFOLIO=m8_control
```

The default is `r2_validated`.

## Delivered

- Central production portfolio configuration.
- Consumer-specific live artifact selection.
- Transfer endpoint metadata identifying the active model and portfolio.
- General planner metadata identifying all consumer assignments.
- Chip recommendation metadata identifying the chip model and portfolio.
- `/api/operations/portfolio` operational status endpoint.
- Explicit rollback portfolio with no automatic transfer or chip execution.
- Optional live shadow comparison against the rollback control.
- Append-only JSONL shadow audit records containing model, portfolio, rules,
  cutoff, projection, recommendation, and delta metadata.
- Shadow failures do not alter or block the active recommendation.

## Shadow operation

Enable with:

```text
FPL_SHADOW_MODE=1
```

The planner shadow compares active versus control projected points. The chip
shadow compares selected chip, expected horizon gain, and projection model.
Records default to:

```text
data/processed/live_shadow_audit.jsonl
```

The path can be overridden with `FPL_SHADOW_AUDIT_PATH`. Shadow mode is
diagnostic only; it never executes a transfer, chip, or automatic rollback.

## Validation

- R3.1 focused tests: `32 passed`.
- Shadow and portfolio focused tests: `36 passed`.
- Full test suite: `164 passed`.
- Ruff: clean.
- `git diff --check`: clean apart from normal Windows line-ending warnings.
- Existing M8.6.1 controls and R2 benchmark results remain unchanged.

## Acceptance decision

R3 passes. The live app now uses the same validated consumer routing as the R2
benchmark, exposes a deterministic rollback, and can observe live divergence
without changing user recommendations. R4 can address the next optimizer or
forecasting improvement using this controlled foundation.
