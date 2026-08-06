# Recovery R1 — Champion/Challenger Decision Audit

## Status

Implemented and verified. R1 adds diagnostics only; it does not change the
accepted M8.6.1 champion, beam planner, chip simulator, or production routing.

## Purpose

The failed M2, M5, M7, M9, and M10 candidates showed that lower prediction error
does not automatically produce better FPL decisions. R1 therefore separates:

- player ranking and return-band quality;
- starting-XI and transfer outcomes;
- captain regret and captain top-two coverage;
- chip action changes and chip-aware season outcomes;
- Blank, Double, and normal Gameweek performance.

## Delivered contract

`decision_audit.py` provides:

- `build_prediction_audit` for realised player points, ranks, return bands,
  MAE/RMSE, rank correlation, and top-k precision/recall;
- `build_decision_audit` for per-Gameweek captain regret, fallback usage,
  captain rank, Blank/Double classification, and existing benchmark actions;
- `build_champion_challenger_report` for aligned per-Gameweek deltas,
  season summaries, regime summaries, and explicit promotion guardrails;
- `ChampionChallengerGate` requiring improvement in at least two validation
  seasons with no severe seasonal regression.

The audit consumes existing benchmark results and does not make decisions.

## Verification

- Focused R1 tests: `5 passed`.
- Real persisted M8.6.1 decision rows audited for 2023/24, 2024/25, and
  2025/26.
- Full pytest: `150 passed`.
- Ruff: clean.
- Existing benchmark controls and persisted history tests remain unchanged.

The audit reported the accepted M8.6.1 captain-regret totals as 274, 220, and
180 points for 2023/24, 2024/25, and 2025/26 respectively. These are diagnostic
baselines, not hindsight targets or production guarantees.

## Promotion guardrails

A challenger remains experimental unless it:

1. improves realistic points in at least two validation seasons;
2. avoids a seasonal regression greater than both the configured absolute and
   percentage guardrails;
3. is evaluated through the chip-aware track when chips are in scope;
4. does not hide captain, transfer, or Blank/Double regressions behind an
   aggregate score.

## Recovery finding carried into R2

A single model must not be assumed safe for transfers, captaincy, and chips at
the same time. The next recovery phase should use this audit to test
consumer-specific challengers with the M8.6.1 champion as the fallback.
