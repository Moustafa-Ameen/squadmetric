"""Point-in-time FPL chip state, legality, scoring, and baseline planning.

The benchmark uses this module as a deliberately deterministic control.  It
does not select chips from realised points: all planner inputs are projections
available at the deadline, while realised points are used only after the
decision has been persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from fpl_intelligence.price_economics import initialise_squad_economics
from fpl_intelligence.season_rules import SeasonRules
from fpl_intelligence.squad_optimizer import optimize_squad, optimize_starting_xi

CHIP_MODE_NONE = "none"
CHIP_MODE_BASELINE = "baseline_planner"
CHIP_MODE_BEAM = "beam_search"
CHIP_MODES = (CHIP_MODE_NONE, CHIP_MODE_BASELINE, CHIP_MODE_BEAM)
CHIP_NAMES = ("wildcard", "freehit", "bboost", "3xc", "assistant_manager")


def normalize_chip_name(value: object) -> str:
    return str(value or "").lower().replace("_", "").replace(" ", "")


def chip_replaces_ordinary_transfer(chip: ChipDefinition | None) -> bool:
    """Return whether a chip branch replaces, rather than accompanies, transfers."""

    return chip is not None and chip.name in {"wildcard", "freehit"}


@dataclass(frozen=True)
class ChipDefinition:
    name: str
    number: int
    start_event: int
    stop_event: int
    duration_gameweeks: int = 1
    permanent_transfers: bool = False
    free_hit_reversion: bool = False
    bench_points_included: bool = False
    captain_multiplier: int = 2
    blocks_other_chips: bool = False

    @property
    def key(self) -> str:
        return f"{self.name}:{self.number}"


@dataclass(frozen=True)
class ChipState:
    season: str
    rules_version: str
    remaining: tuple[str, ...]
    used: tuple[str, ...] = ()
    used_gameweeks: tuple[tuple[int, str], ...] = ()
    active_until: int | None = None

    def used_at(self, gameweek: int) -> bool:
        return any(gw == gameweek for gw, _ in self.used_gameweeks)


@dataclass(frozen=True)
class ChipCounterfactual:
    chip_key: str
    chip_number: int | None
    legal: bool
    expected_gameweek_points: float
    no_chip_gameweek_points: float
    expected_gain: float
    status: str
    reason: str
    expected_horizon_points: float = 0.0
    no_chip_horizon_points: float = 0.0
    future_opportunity_cost: float = 0.0
    uncertainty_penalty: float = 0.0


@dataclass(frozen=True)
class ChipDecision:
    gameweek: int
    chip_name: str = "none"
    chip_number: int | None = None
    expected_points: float = 0.0
    no_chip_expected_points: float = 0.0
    expected_gain: float = 0.0
    decision_status: str = "not_used"
    reason: str = ""
    expected_gameweek_points: float = 0.0
    expected_horizon_points: float = 0.0
    no_chip_horizon_points: float = 0.0
    future_opportunity_cost: float = 0.0
    uncertainty_penalty: float = 0.0
    counterfactuals: tuple[ChipCounterfactual, ...] = ()

    @property
    def chip_key(self) -> str:
        if self.chip_number is None:
            return "none"
        return f"{self.chip_name}:{self.chip_number}"


def chip_definitions(rules: SeasonRules) -> tuple[ChipDefinition, ...]:
    """Convert a manifest into a stable typed chip contract."""

    definitions: list[ChipDefinition] = []
    for raw in rules.chips:
        name = normalize_chip_name(raw.get("name"))
        if name not in CHIP_NAMES:
            continue
        start = int(raw.get("start_event") or 1)
        stop = int(raw.get("stop_event") or 38)
        definitions.append(
            ChipDefinition(
                name=name,
                number=int(raw.get("number") or 1),
                start_event=start,
                stop_event=stop,
                duration_gameweeks=int(raw.get("duration_gameweeks") or 1),
                permanent_transfers=bool(raw.get("permanent_transfers", False)),
                free_hit_reversion=bool(raw.get("free_hit_reversion", False)),
                bench_points_included=bool(raw.get("bench_points_included", False)),
                captain_multiplier=int(raw.get("captain_multiplier") or 2),
                blocks_other_chips=bool(raw.get("blocks_other_chips", False)),
            )
        )
    return tuple(sorted(definitions, key=lambda chip: (chip.start_event, chip.name, chip.number)))


def initial_chip_state(rules: SeasonRules) -> ChipState:
    return ChipState(
        season=rules.season,
        rules_version=rules.rules_version,
        remaining=tuple(chip.key for chip in chip_definitions(rules)),
    )


def legal_chip_options(
    state: ChipState,
    gameweek: int,
    rules: SeasonRules,
) -> tuple[ChipDefinition, ...]:
    """Return chips legal at a deadline, excluding the implicit no-chip action."""

    if state.used_at(gameweek):
        return ()
    if state.active_until is not None and gameweek <= state.active_until:
        return ()
    definitions = {chip.key: chip for chip in chip_definitions(rules)}
    options = []
    for key in state.remaining:
        chip = definitions[key]
        if not chip.start_event <= gameweek <= chip.stop_event:
            continue
        # The 2026/27 rule forbids using the second Free Hit in GW20 when the
        # first was played in GW19.  Keeping this tied to chip numbers makes it
        # explicit and avoids season-name inference in the simulator.
        if (
            chip.name == "freehit"
            and chip.number == 2
            and gameweek == 20
            and (19, "freehit:1") in state.used_gameweeks
        ):
            continue
        options.append(chip)
    return tuple(options)


def apply_chip(
    state: ChipState,
    chip: ChipDefinition,
    gameweek: int,
    rules: SeasonRules,
) -> ChipState:
    if chip.key not in state.remaining:
        raise ValueError(f"Chip {chip.key} is not available")
    if chip not in legal_chip_options(state, gameweek, rules):
        raise ValueError(f"Chip {chip.key} is not legal in GW{gameweek}")
    remaining = tuple(key for key in state.remaining if key != chip.key)
    active_until = gameweek + chip.duration_gameweeks - 1 if chip.duration_gameweeks > 1 else None
    return replace(
        state,
        remaining=remaining,
        used=(*state.used, chip.key),
        used_gameweeks=(*state.used_gameweeks, (gameweek, chip.key)),
        active_until=active_until,
    )


def _actual_points(target: pd.DataFrame) -> dict[int, float]:
    rows = target.drop_duplicates("player_id").set_index("player_id")
    return {
        int(player_id): float(value)
        for player_id, value in rows["next_gameweek_points"].items()
        if pd.notna(value)
    }


def apply_chip_to_score(
    base_points: float,
    captain_actual_points: float,
    *,
    chip: ChipDefinition | None,
    bench_points: float = 0.0,
) -> float:
    """Apply the score-only chip effects to an already legal lineup score."""

    if chip is None:
        return float(base_points)
    total = float(base_points)
    if chip.captain_multiplier == 3:
        total += float(captain_actual_points)
    if chip.bench_points_included:
        total += float(bench_points)
    return total


def bench_points_not_autosubbed(
    target: pd.DataFrame,
    bench_ids: tuple[int, ...],
    autosub_ids: tuple[int, ...],
) -> float:
    points = _actual_points(target)
    return float(
        sum(
            points.get(player_id, 0.0)
            for player_id in bench_ids
            if player_id not in autosub_ids
        )
    )


def build_chip_squad(
    predictions: pd.DataFrame,
    *,
    budget: float,
    prediction_column: str = "expected_points_adjusted",
) -> pd.DataFrame:
    """Build a legal wildcard/free-hit squad from deadline-safe projections."""

    working = predictions.copy()
    if "decision_price" in working:
        working["price"] = pd.to_numeric(working["decision_price"], errors="coerce").fillna(
            pd.to_numeric(working["price"], errors="coerce")
        )
    return initialise_squad_economics(
        optimize_squad(
            working,
            prediction_column=prediction_column,
            budget=float(budget),
        )
    )


def apply_squad_transition(
    original_squad: pd.DataFrame,
    chip_squad: pd.DataFrame,
    chip: ChipDefinition,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the active GW squad and the squad retained after the GW."""

    if chip.name not in {"wildcard", "freehit"}:
        raise ValueError(f"{chip.name} does not replace the active squad")
    active = chip_squad.copy()
    retained = original_squad.copy() if chip.free_hit_reversion else active.copy()
    return active, retained


def projected_squad_value(squad: pd.DataFrame, projections: dict[int, float]) -> float:
    """Return expected FPL points for one GW, including normal captaincy."""

    value, _, _, _ = _gameweek_value(squad, projections)
    return value


@dataclass(frozen=True)
class _ChipValuation:
    chip: ChipDefinition
    active_squad: pd.DataFrame | None
    expected_gameweek_points: float
    expected_horizon_points: float
    no_chip_gameweek_points: float
    no_chip_horizon_points: float
    future_opportunity_cost: float
    uncertainty_penalty: float
    reason: str

    @property
    def expected_gain(self) -> float:
        return self.expected_horizon_points - self.no_chip_horizon_points

    @property
    def guarded_gain(self) -> float:
        return self.expected_gain - self.future_opportunity_cost - self.uncertainty_penalty


class DeterministicChipPlanner:
    """Small receding-horizon chip planner used as the M8 benchmark control."""

    name = "deterministic-chip-planner"
    version = "m8-chip-valuation-v1"

    def decide(
        self,
        state: ChipState,
        gameweek: int,
        squad: pd.DataFrame,
        predictions: pd.DataFrame,
        future_predictions: dict[int, pd.DataFrame],
        *,
        bank: float,
        rules: SeasonRules,
        no_chip_squad: pd.DataFrame | None = None,
        no_chip_bank: float | None = None,
    ) -> tuple[ChipDecision, ChipDefinition | None, pd.DataFrame | None]:
        scoring_squad = no_chip_squad if no_chip_squad is not None else squad
        current_projections = _projection_map(predictions)
        horizon_frames = _horizon_frames(
            predictions,
            future_predictions,
            gameweek=gameweek,
            horizon_length=8,
        )
        no_chip_current, no_chip_lineup, no_chip_captain, no_chip_bench = _gameweek_value(
            scoring_squad, current_projections
        )
        no_chip_horizon = _squad_horizon_value(scoring_squad, horizon_frames)
        candidates: list[_ChipValuation] = []
        counterfactuals = [
            ChipCounterfactual(
                chip_key="none",
                chip_number=None,
                legal=True,
                expected_gameweek_points=no_chip_current,
                no_chip_gameweek_points=no_chip_current,
                expected_gain=0.0,
                status="control",
                reason="no chip selected",
                expected_horizon_points=no_chip_horizon,
                no_chip_horizon_points=no_chip_horizon,
            )
        ]
        budget = float(pd.to_numeric(squad["price"], errors="coerce").sum()) + float(bank)
        for chip in legal_chip_options(state, gameweek, rules):
            valuation = self._value_chip(
                chip,
                gameweek=gameweek,
                squad=squad,
                scoring_squad=scoring_squad,
                predictions=predictions,
                future_predictions=future_predictions,
                horizon_frames=horizon_frames,
                budget=budget,
                no_chip_current=no_chip_current,
                no_chip_horizon=no_chip_horizon,
                no_chip_lineup=no_chip_lineup,
                no_chip_captain=no_chip_captain,
                no_chip_bench=no_chip_bench,
            )
            if valuation is None:
                counterfactuals.append(
                    ChipCounterfactual(
                        chip_key=chip.key,
                        chip_number=chip.number,
                        legal=True,
                        expected_gameweek_points=no_chip_current,
                        no_chip_gameweek_points=no_chip_current,
                        expected_gain=0.0,
                        status="not_evaluated",
                        reason="historical Assistant Manager scoring requires manager data",
                        expected_horizon_points=no_chip_horizon,
                        no_chip_horizon_points=no_chip_horizon,
                    )
                )
                continue
            candidates.append(valuation)
            counterfactuals.append(
                ChipCounterfactual(
                    chip_key=chip.key,
                    chip_number=chip.number,
                    legal=True,
                    expected_gameweek_points=valuation.expected_gameweek_points,
                    no_chip_gameweek_points=valuation.no_chip_gameweek_points,
                    expected_gain=(
                        valuation.expected_gameweek_points
                        - valuation.no_chip_gameweek_points
                    ),
                    status="evaluated",
                    reason=valuation.reason,
                    expected_horizon_points=valuation.expected_horizon_points,
                    no_chip_horizon_points=valuation.no_chip_horizon_points,
                    future_opportunity_cost=valuation.future_opportunity_cost,
                    uncertainty_penalty=valuation.uncertainty_penalty,
                )
            )
        if not candidates:
            counterfactuals = tuple(
                replace(
                    value,
                    status="selected" if value.chip_key == "none" else "rejected",
                    reason=(
                        "selected no-chip control"
                        if value.chip_key == "none"
                        else "rejected: no legal positive-value chip opportunity"
                    ),
                )
                for value in counterfactuals
            )
            return (
                ChipDecision(
                    gameweek=gameweek,
                    no_chip_expected_points=no_chip_current,
                    expected_gameweek_points=no_chip_current,
                    expected_horizon_points=no_chip_horizon,
                    no_chip_horizon_points=no_chip_horizon,
                    counterfactuals=tuple(counterfactuals),
                ),
                None,
                None,
            )

        best = max(
            candidates,
            key=lambda item: (
                item.guarded_gain,
                item.expected_gain,
                -item.chip.number,
                item.chip.name,
            ),
        )
        if best.guarded_gain <= 0:
            reason = (
                "rejected: no positive projected gain"
                if best.expected_gain <= 0
                else "rejected: future opportunity or uncertainty is stronger than current gain"
            )
            counterfactuals = tuple(
                replace(
                    value,
                    status="selected" if value.chip_key == "none" else "rejected",
                    reason=("selected no-chip control" if value.chip_key == "none" else reason),
                )
                for value in counterfactuals
            )
            return (
                ChipDecision(
                    gameweek=gameweek,
                    no_chip_expected_points=no_chip_current,
                    expected_gameweek_points=no_chip_current,
                    expected_horizon_points=no_chip_horizon,
                    no_chip_horizon_points=no_chip_horizon,
                    reason=reason,
                    counterfactuals=tuple(counterfactuals),
                ),
                None,
                None,
            )
        counterfactuals = tuple(
            replace(
                value,
                status="selected" if value.chip_key == best.chip.key else "rejected",
                reason=(
                    f"selected: {best.reason}"
                    if value.chip_key == best.chip.key
                    else "rejected: another legal action had higher guarded value"
                ),
            )
            for value in counterfactuals
        )
        decision = ChipDecision(
            gameweek=gameweek,
            chip_name=best.chip.name,
            chip_number=best.chip.number,
            expected_points=float(best.expected_gameweek_points),
            no_chip_expected_points=float(best.no_chip_gameweek_points),
            expected_gain=float(best.expected_gain),
            decision_status="planned",
            reason=best.reason,
            expected_gameweek_points=float(best.expected_gameweek_points),
            expected_horizon_points=float(best.expected_horizon_points),
            no_chip_horizon_points=float(best.no_chip_horizon_points),
            future_opportunity_cost=float(best.future_opportunity_cost),
            uncertainty_penalty=float(best.uncertainty_penalty),
            counterfactuals=counterfactuals,
        )
        return decision, best.chip, best.active_squad

    def _value_chip(
        self,
        chip: ChipDefinition,
        *,
        gameweek: int,
        squad: pd.DataFrame,
        scoring_squad: pd.DataFrame,
        predictions: pd.DataFrame,
        future_predictions: dict[int, pd.DataFrame],
        horizon_frames: list[tuple[int, pd.DataFrame]],
        budget: float,
        no_chip_current: float,
        no_chip_horizon: float,
        no_chip_lineup: Any,
        no_chip_captain: float,
        no_chip_bench: float,
    ) -> _ChipValuation | None:
        if chip.name == "assistant_manager":
            manager_points = _assistant_manager_expected_points(predictions)
            if manager_points is None:
                return None
            return _ChipValuation(
                chip=chip,
                active_squad=None,
                expected_gameweek_points=no_chip_current + manager_points,
                expected_horizon_points=no_chip_horizon + manager_points,
                no_chip_gameweek_points=no_chip_current,
                no_chip_horizon_points=no_chip_horizon,
                future_opportunity_cost=0.0,
                uncertainty_penalty=0.0,
                reason="historical Assistant Manager projection with official scoring contract",
            )

        if chip.name == "wildcard":
            chip_horizon = 8
            frames = horizon_frames[:chip_horizon]
            candidates = _aggregate_horizon_candidates(
                predictions, future_predictions, gameweek, chip_horizon
            )
            candidate_squad = build_chip_squad(
                candidates,
                budget=budget,
                prediction_column="horizon_expected_points",
            )
            expected_horizon = _squad_horizon_value(candidate_squad, frames)
            expected_gameweek, _, _, _ = _gameweek_value(
                candidate_squad, _projection_map(predictions)
            )
            penalty = _uncertainty_penalty(candidate_squad, frames)
            return _ChipValuation(
                chip=chip,
                active_squad=candidate_squad,
                expected_gameweek_points=expected_gameweek,
                expected_horizon_points=expected_horizon,
                no_chip_gameweek_points=no_chip_current,
                no_chip_horizon_points=no_chip_horizon,
                future_opportunity_cost=0.0,
                uncertainty_penalty=penalty,
                reason="permanent squad selected over an 8-Gameweek horizon",
            )

        if chip.name == "freehit":
            chip_horizon = 3
            frames = horizon_frames[:chip_horizon]
            candidate_squad = build_chip_squad(predictions, budget=budget)
            expected_gameweek, _, _, _ = _gameweek_value(
                candidate_squad, _projection_map(predictions)
            )
            retained_future = _squad_horizon_value(scoring_squad, frames[1:])
            expected_horizon = expected_gameweek + retained_future
            no_chip_future = _squad_horizon_value(scoring_squad, frames[1:])
            future_opportunity = _future_free_hit_opportunity(
                scoring_squad,
                future_predictions,
                budget=budget,
                gameweek=gameweek,
            )
            penalty = _uncertainty_penalty(candidate_squad, frames[:1])
            return _ChipValuation(
                chip=chip,
                active_squad=candidate_squad,
                expected_gameweek_points=expected_gameweek,
                expected_horizon_points=expected_horizon,
                no_chip_gameweek_points=no_chip_current,
                no_chip_horizon_points=no_chip_current + no_chip_future,
                future_opportunity_cost=future_opportunity,
                uncertainty_penalty=penalty,
                reason="temporary squad compared over the current Blank/Double-aware horizon",
            )

        if chip.name == "bboost":
            chip_horizon = 3
            frames = horizon_frames[:chip_horizon]
            expected_gameweek = no_chip_current + no_chip_bench
            future_opportunity = _future_bench_opportunity(scoring_squad, frames[1:])
            penalty = _uncertainty_penalty(scoring_squad, frames[:1], include_bench=True)
            return _ChipValuation(
                chip=chip,
                active_squad=None,
                expected_gameweek_points=expected_gameweek,
                expected_horizon_points=no_chip_horizon + no_chip_bench,
                no_chip_gameweek_points=no_chip_current,
                no_chip_horizon_points=no_chip_horizon,
                future_opportunity_cost=future_opportunity,
                uncertainty_penalty=penalty,
                reason="all four bench players valued with current fixture and minutes projections",
            )

        if chip.name == "3xc":
            chip_horizon = 3
            frames = horizon_frames[:chip_horizon]
            future_opportunity = _future_captain_opportunity(scoring_squad, frames[1:])
            penalty = _uncertainty_penalty(scoring_squad, frames[:1])
            return _ChipValuation(
                chip=chip,
                active_squad=None,
                expected_gameweek_points=no_chip_current + no_chip_captain,
                expected_horizon_points=no_chip_horizon + no_chip_captain,
                no_chip_gameweek_points=no_chip_current,
                no_chip_horizon_points=no_chip_horizon,
                future_opportunity_cost=future_opportunity,
                uncertainty_penalty=penalty,
                reason="captain expected points valued with a three-Gameweek opportunity guardrail",
            )
        return None


def _projection_map(frame: pd.DataFrame) -> dict[int, float]:
    if frame.empty:
        return {}
    return {
        int(player_id): float(value)
        for player_id, value in frame.drop_duplicates("player_id")
        .set_index("player_id")["expected_points_adjusted"]
        .fillna(0.0)
        .items()
    }


def _gameweek_value(
    squad: pd.DataFrame,
    projections: dict[int, float],
) -> tuple[float, Any, float, float]:
    lineup = optimize_starting_xi(squad, projections)
    starter_points = float(
        sum(projections.get(player_id, 0.0) for player_id in lineup.starting_ids)
    )
    captain = max(
        (float(projections.get(player_id, 0.0)) for player_id in lineup.starting_ids),
        default=0.0,
    )
    bench = float(sum(projections.get(player_id, 0.0) for player_id in lineup.bench_ids))
    return starter_points + captain, lineup, captain, bench


def _horizon_frames(
    predictions: pd.DataFrame,
    future_predictions: dict[int, pd.DataFrame],
    *,
    gameweek: int,
    horizon_length: int,
) -> list[tuple[int, pd.DataFrame]]:
    frames = [(gameweek, predictions)]
    for target_gameweek in range(gameweek + 1, gameweek + horizon_length):
        frames.append((target_gameweek, future_predictions.get(target_gameweek, pd.DataFrame())))
    return frames


def _squad_horizon_value(
    squad: pd.DataFrame,
    frames: list[tuple[int, pd.DataFrame]],
) -> float:
    return float(sum(_gameweek_value(squad, _projection_map(frame))[0] for _, frame in frames))


def _aggregate_horizon_candidates(
    predictions: pd.DataFrame,
    future_predictions: dict[int, pd.DataFrame],
    gameweek: int,
    horizon_length: int,
) -> pd.DataFrame:
    frames = _horizon_frames(
        predictions,
        future_predictions,
        gameweek=gameweek,
        horizon_length=horizon_length,
    )
    available = [
        frame.assign(_frame_order=order)
        for order, (_, frame) in enumerate(frames)
        if not frame.empty
    ]
    if not available:
        raise ValueError("No projections available for chip horizon")
    combined = pd.concat(available, ignore_index=True, sort=False)
    values = (
        combined.groupby("player_id", as_index=False)["expected_points_adjusted"]
        .sum()
        .rename(columns={"expected_points_adjusted": "horizon_expected_points"})
    )
    metadata = combined.sort_values(["_frame_order", "player_id"]).drop_duplicates("player_id")
    return metadata.merge(values, on="player_id", how="inner")


def _uncertainty_penalty(
    squad: pd.DataFrame,
    frames: list[tuple[int, pd.DataFrame]],
    *,
    include_bench: bool = False,
) -> float:
    penalty = 0.0
    for _, frame in frames:
        if frame.empty:
            continue
        projection = _projection_map(frame)
        _, lineup, _, _ = _gameweek_value(squad, projection)
        ids = lineup.starting_ids + (lineup.bench_ids if include_bench else ())
        probabilities = (
            frame.drop_duplicates("player_id")
            .set_index("player_id")
            .get("probability_60_plus_minutes", pd.Series(dtype=float))
        )
        for player_id in ids:
            expected = max(0.0, projection.get(player_id, 0.0))
            probability = float(probabilities.get(player_id, 1.0))
            penalty += expected * max(0.0, 1.0 - probability) * 0.05
    return float(penalty)


def _future_captain_opportunity(
    squad: pd.DataFrame,
    frames: list[tuple[int, pd.DataFrame]],
) -> float:
    return max(
        (
            _gameweek_value(squad, _projection_map(frame))[2]
            for _, frame in frames
            if not frame.empty
        ),
        default=0.0,
    )


def _future_bench_opportunity(
    squad: pd.DataFrame,
    frames: list[tuple[int, pd.DataFrame]],
) -> float:
    return max(
        (
            _gameweek_value(squad, _projection_map(frame))[3]
            for _, frame in frames
            if not frame.empty
        ),
        default=0.0,
    )


def _future_free_hit_opportunity(
    squad: pd.DataFrame,
    future_predictions: dict[int, pd.DataFrame],
    *,
    budget: float,
    gameweek: int,
) -> float:
    opportunities = []
    for target_gameweek, frame in sorted(future_predictions.items()):
        if target_gameweek > gameweek + 7 or frame.empty:
            continue
        try:
            candidate = build_chip_squad(frame, budget=budget)
        except ValueError:
            continue
        candidate_value = _gameweek_value(candidate, _projection_map(frame))[0]
        retained_value = _gameweek_value(squad, _projection_map(frame))[0]
        opportunities.append(max(0.0, candidate_value - retained_value))
    return max(opportunities, default=0.0)


def _assistant_manager_expected_points(projection: pd.DataFrame) -> float | None:
    """Evaluate the historical Assistant Manager contract when supplied."""

    required = {"manager_wins", "manager_draws", "manager_goals", "manager_clean_sheets"}
    if not required.issubset(projection.columns):
        return None
    row = projection.iloc[0]
    table_bonus = float(row.get("manager_table_bonus", 0.0) or 0.0)
    return float(
        6 * float(row["manager_wins"] or 0)
        + 3 * float(row["manager_draws"] or 0)
        + float(row["manager_goals"] or 0)
        + 2 * float(row["manager_clean_sheets"] or 0)
        + table_bonus
    )


def assistant_manager_expected_points(
    *,
    wins: float,
    draws: float,
    team_goals: float,
    clean_sheets: float,
    table_bonus: float = 0.0,
) -> float:
    """Return the official historical Assistant Manager expected points."""

    return float(6 * wins + 3 * draws + team_goals + 2 * clean_sheets + table_bonus)
