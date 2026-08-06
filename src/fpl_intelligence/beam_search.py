"""Deterministic receding-horizon beam search for complete FPL decisions.

This remains an experimental M8 planner. It searches legal transfers and chips
jointly over a short horizon, with horizon-aware permanent-chip valuation and
explicit root counterfactuals for benchmark and live consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from fpl_intelligence.backtest_transfer_strategy import (
    MAX_PLAYERS_PER_TEAM,
    TransferDecision,
    position_group,
    validate_squad,
)
from fpl_intelligence.chip_simulation import (
    ChipDefinition,
    ChipState,
    _assistant_manager_expected_points,
    _projection_map,
    apply_chip,
    build_chip_squad,
    legal_chip_options,
)
from fpl_intelligence.season_rules import SeasonRules
from fpl_intelligence.squad_optimizer import VALID_FORMATIONS

HIT_POLICIES = ("current_gw", "horizon_value")


@dataclass(frozen=True)
class DecisionState:
    """Complete state carried by one beam-search branch."""

    gameweek: int
    squad: pd.DataFrame
    starting_xi: tuple[int, ...]
    bench_order: tuple[int, ...]
    captain: int | None
    vice_captain: int | None
    bank: float
    free_transfers: int
    transfer_hits: int
    remaining_chips: ChipState
    active_chip: str | None
    fixture_scenario: Any | None
    rules_version: str
    score: float = 0.0
    first_action: BeamAction | None = None


@dataclass(frozen=True)
class BeamAction:
    transfer: TransferDecision
    chip: ChipDefinition | None
    chip_squad: pd.DataFrame | None
    expected_points: float
    search_score: float
    reason: str
    no_chip_expected_points: float = 0.0
    expected_horizon_points: float = 0.0
    no_chip_horizon_points: float = 0.0
    future_opportunity_cost: float = 0.0
    uncertainty_penalty: float = 0.0
    transfer_expected_horizon_gain: float = 0.0
    transfer_expected_horizon_net_gain: float = 0.0
    hit_policy: str = "current_gw"


@dataclass(frozen=True)
class _FastLineup:
    starting_ids: tuple[int, ...]
    bench_ids: tuple[int, ...]
    formation: str


class DeterministicBeamPlanner:
    """Search legal transfer/chip branches with stable pruning and tie-breaks."""

    name = "deterministic-beam-search"
    version = "m8-beam-v1"

    def __init__(
        self,
        *,
        beam_width: int = 6,
        horizon: int = 3,
        max_transfers: int = 6,
        hit_policy: str = "current_gw",
    ):
        if beam_width < 1 or horizon < 1 or max_transfers < 1:
            raise ValueError("beam_width, horizon, and max_transfers must be positive")
        if hit_policy not in HIT_POLICIES:
            raise ValueError(f"hit_policy must be one of {', '.join(HIT_POLICIES)}")
        self.beam_width = beam_width
        self.horizon = horizon
        self.max_transfers = max_transfers
        self.hit_policy = hit_policy
        self._chip_squad_cache: dict[tuple[Any, ...], pd.DataFrame] = {}
        self._projection_cache: dict[int, dict[int, float]] = {}
        self.last_counterfactuals: tuple[BeamAction, ...] = ()

    def decide(
        self,
        *,
        gameweek: int,
        squad: pd.DataFrame,
        bank: float,
        free_transfers: int,
        chip_state: ChipState,
        predictions: pd.DataFrame,
        future_predictions: dict[int, pd.DataFrame],
        chip_predictions: pd.DataFrame | None = None,
        future_chip_predictions: dict[int, pd.DataFrame] | None = None,
        rules: SeasonRules,
        fixture_scenario: Any | None = None,
    ) -> BeamAction:
        """Return the first action from the best deterministic beam path."""

        chip_predictions = chip_predictions if chip_predictions is not None else predictions
        future_chip_predictions = (
            future_chip_predictions
            if future_chip_predictions is not None
            else future_predictions
        )
        projection = _projection_map(predictions)
        self._chip_squad_cache = {}
        self._projection_cache = {
            id(predictions): projection,
            id(chip_predictions): _projection_map(chip_predictions),
        }
        self.last_counterfactuals = ()
        lineup = _fast_lineup(squad, projection)
        root = DecisionState(
            gameweek=gameweek,
            squad=squad.copy(),
            starting_xi=lineup.starting_ids,
            bench_order=lineup.bench_ids,
            captain=_captain_ids(lineup.starting_ids, projection)[0],
            vice_captain=_captain_ids(lineup.starting_ids, projection)[1],
            bank=float(bank),
            free_transfers=int(free_transfers),
            transfer_hits=0,
            remaining_chips=chip_state,
            active_chip=None,
            fixture_scenario=fixture_scenario,
            rules_version=rules.rules_version,
        )
        frames = {gameweek: predictions, **future_predictions}
        chip_frames = {gameweek: chip_predictions, **future_chip_predictions}
        beam = [root]
        for offset in range(self.horizon):
            target_gameweek = gameweek + offset
            frame = frames.get(target_gameweek, pd.DataFrame())
            chip_frame = chip_frames.get(target_gameweek, pd.DataFrame())
            next_beam: list[DecisionState] = []
            for state in beam:
                branches = self._expand_state(
                    state,
                    frame,
                    frames,
                    rules,
                    chip_predictions=chip_frame,
                    chip_frames=chip_frames,
                )
                next_beam.extend(branches)
                if offset == 0:
                    self.last_counterfactuals = _deduplicate_actions(
                        [branch.first_action for branch in next_beam if branch.first_action]
                    )
            if not next_beam:
                break
            next_beam.sort(key=_state_sort_key)
            beam = next_beam[: self.beam_width]

        if not beam or beam[0].first_action is None:
            return BeamAction(
                transfer=_empty_transfer_decision(),
                chip=None,
                chip_squad=None,
                expected_points=0.0,
                search_score=0.0,
                reason="no legal beam branch",
            )
        return beam[0].first_action

    def _expand_state(
        self,
        state: DecisionState,
        predictions: pd.DataFrame,
        frames: dict[int, pd.DataFrame],
        rules: SeasonRules,
        *,
        chip_predictions: pd.DataFrame,
        chip_frames: dict[int, pd.DataFrame],
    ) -> list[DecisionState]:
        if predictions.empty:
            return []
        future = {
            gameweek: frame
            for gameweek, frame in frames.items()
            if gameweek > state.gameweek
        }
        future_chip = {
            gameweek: frame
            for gameweek, frame in chip_frames.items()
            if gameweek > state.gameweek
        }
        is_first_action = state.first_action is None
        ranking_mode = self.hit_policy if is_first_action else "current_gw"
        transfer_options = (
            [_empty_transfer_decision()]
            if state.gameweek == 1
            else generate_transfer_options(
                state.squad,
                predictions,
                bank=state.bank,
                free_transfers=state.free_transfers,
                max_options=self.max_transfers if is_first_action else 6,
                future_predictions=future,
                ranking_mode=ranking_mode,
            )
        )
        chips: list[ChipDefinition | None] = [None]
        chips.extend(legal_chip_options(state.remaining_chips, state.gameweek, rules))
        branches: list[DecisionState] = []
        for chip in chips:
            if chip is not None and chip.name == "assistant_manager":
                if _assistant_manager_expected_points(chip_predictions) is None:
                    continue
            if chip is not None and chip.name in {"wildcard", "freehit"}:
                try:
                    budget = state.bank + float(state.squad["price"].sum())
                    chip_squad = self._build_chip_squad(
                        chip_predictions,
                        squad=state.squad,
                        chip=chip,
                        budget=budget,
                        future_predictions=future_chip,
                    )
                except ValueError:
                    continue
                transfer_options_for_chip = [_empty_transfer_decision()]
            else:
                chip_squad = None
                transfer_options_for_chip = transfer_options

            for transfer in transfer_options_for_chip:
                branches.append(
                    self._transition(
                        state,
                        predictions,
                        future,
                        rules,
                        chip_predictions=chip_predictions,
                        chip_future=future_chip,
                        transfer=transfer,
                        chip=chip,
                        chip_squad=chip_squad,
                    )
                )
        return branches

    def _build_chip_squad(
        self,
        predictions: pd.DataFrame,
        *,
        squad: pd.DataFrame,
        chip: ChipDefinition,
        budget: float,
        future_predictions: dict[int, pd.DataFrame],
    ) -> pd.DataFrame:
        prediction_gameweek = (
            int(predictions["gameweek"].iloc[0])
            if "gameweek" in predictions
            else 0
        )
        squad_signature = tuple(sorted(int(value) for value in squad["player_id"]))
        key = (prediction_gameweek, chip.name, round(budget, 1), squad_signature)
        if key not in self._chip_squad_cache:
            candidates = _prune_candidates(
                predictions,
                squad,
                future_predictions=future_predictions,
            )
            if chip.name == "wildcard":
                candidates = _aggregate_horizon_predictions(
                    candidates,
                    future_predictions,
                    minimum_gameweeks=6,
                )
            self._chip_squad_cache[key] = build_chip_squad(candidates, budget=budget)
        return self._chip_squad_cache[key].copy()

    def _transition(
        self,
        state: DecisionState,
        predictions: pd.DataFrame,
        future: dict[int, pd.DataFrame],
        rules: SeasonRules,
        *,
        chip_predictions: pd.DataFrame,
        chip_future: dict[int, pd.DataFrame],
        transfer: TransferDecision,
        chip: ChipDefinition | None,
        chip_squad: pd.DataFrame | None,
    ) -> DecisionState:
        before_squad = state.squad.copy()
        after_transfer = _apply_transfer(before_squad, predictions, transfer)
        bank_after_transfer = round(
            state.bank
            + float(transfer.outgoing_price or 0.0)
            - float(transfer.incoming_price or 0.0),
            1,
        )
        ft_after_transfer = max(0, state.free_transfers - int(transfer.made))
        active_squad = after_transfer
        retained_squad = after_transfer
        bank_after = bank_after_transfer
        ft_after = ft_after_transfer
        ordinary_transfer = True
        if chip is not None and chip.name in {"wildcard", "freehit"}:
            assert chip_squad is not None
            active_squad = chip_squad.copy()
            ordinary_transfer = False
            if chip.name == "wildcard":
                retained_squad = active_squad.copy()
                budget = state.bank + float(before_squad["price"].sum())
                bank_after = round(budget - float(active_squad["price"].sum()), 1)
                ft_after = state.free_transfers
            else:
                retained_squad = before_squad
                bank_after = state.bank
                ft_after = state.free_transfers

        next_chip_state = state.remaining_chips
        if chip is not None:
            next_chip_state = apply_chip(next_chip_state, chip, state.gameweek, rules)

        transfer_projection = self._projection_for(predictions)
        valuation_predictions = chip_predictions if chip is not None else predictions
        valuation_future = chip_future if chip is not None else future
        projection = self._projection_for(valuation_predictions)
        base_value, lineup, captain, bench = _fast_gameweek_value(active_squad, projection)
        before_value = _fast_gameweek_value(before_squad, projection)[0]
        no_chip_value = _fast_gameweek_value(after_transfer, projection)[0]
        current_transfer_gain = no_chip_value - before_value
        is_first_action = state.first_action is None
        transfer_horizon_gain = (
            _transfer_horizon_gain(
                before_squad,
                after_transfer,
                transfer_projection,
                future,
            )
            if is_first_action
            else 0.0
        )
        chip_value = 0.0
        if chip is not None and chip.name == "bboost":
            chip_value = bench
        elif chip is not None and chip.name == "3xc":
            chip_value = captain
        elif chip is not None and chip.name == "assistant_manager":
            chip_value = _assistant_manager_expected_points(chip_predictions) or 0.0
        expected_points = base_value + chip_value
        if is_first_action:
            future_squads = (
                retained_squad
                if chip is not None and chip.name == "freehit"
                else active_squad
            )
            valuation_horizon = (
                6
                if chip is not None and chip.name == "wildcard"
                else 3
                if chip is not None and chip.name in {"freehit", "bboost", "3xc"}
                else max(self.horizon, 3)
                if self.hit_policy == "horizon_value"
                else self.horizon
            )
            future_frames = [
                frame
                for _, frame in sorted(valuation_future.items())[
                    : max(0, valuation_horizon - 1)
                ]
            ]
            expected_horizon = expected_points + sum(
                _fast_gameweek_value(
                    future_squads,
                    self._projection_for(frame),
                )[0]
                for frame in future_frames
            )
            no_chip_horizon = no_chip_value + sum(
                _fast_gameweek_value(
                    after_transfer,
                    self._projection_for(frame),
                )[0]
                for frame in future_frames
            )
        else:
            expected_horizon = expected_points
            no_chip_horizon = no_chip_value
        uncertainty = _fast_uncertainty_penalty(
            active_squad,
            valuation_predictions,
            lineup,
            include_bench=chip is not None and chip.name == "bboost",
        )
        opportunity_cost = (
            _future_opportunity_cost(
                state.remaining_chips,
                chip=chip,
                future={
                    gameweek: frame
                    for gameweek, frame in valuation_future.items()
                    if gameweek >= state.gameweek + self.horizon
                },
                retained_squad=after_transfer,
                bank_if_saved=bank_after_transfer,
                next_chip_state=next_chip_state,
                rules=rules,
                current_expected_gain=max(
                    0.0,
                    expected_horizon - no_chip_horizon,
                ),
            )
            if is_first_action
            else 0.0
        )
        hit_cost = transfer.hit_cost if ordinary_transfer else 0
        flexibility_value = 0.02 * bank_after + 0.15 * ft_after
        branch_score = (
            expected_points
            - hit_cost
            - uncertainty
            - opportunity_cost
            + flexibility_value
        )
        if (
            self.hit_policy == "horizon_value"
            and is_first_action
            and hit_cost > 0
        ):
            future_incremental_gain = max(
                0.0,
                transfer_horizon_gain - current_transfer_gain,
            )
            branch_score += future_incremental_gain
        if chip is not None and chip.name == "freehit":
            next_squad = retained_squad.copy()
        else:
            next_squad = retained_squad.copy()
        next_ft = min(int(rules.max_free_transfers or 5), ft_after + 1)
        first_action = state.first_action or BeamAction(
            transfer=transfer,
            chip=chip,
            chip_squad=chip_squad.copy() if chip_squad is not None else None,
            expected_points=expected_points,
            search_score=branch_score,
            reason=_branch_reason(transfer, chip),
            no_chip_expected_points=no_chip_value,
            expected_horizon_points=expected_horizon,
            no_chip_horizon_points=no_chip_horizon,
            future_opportunity_cost=opportunity_cost,
            uncertainty_penalty=uncertainty,
            transfer_expected_horizon_gain=transfer_horizon_gain,
            transfer_expected_horizon_net_gain=transfer_horizon_gain - hit_cost,
            hit_policy=self.hit_policy,
        )
        return replace(
            state,
            gameweek=state.gameweek + 1,
            squad=next_squad,
            starting_xi=(),
            bench_order=(),
            captain=None,
            vice_captain=None,
            bank=bank_after,
            free_transfers=next_ft,
            transfer_hits=state.transfer_hits + hit_cost,
            remaining_chips=next_chip_state,
            active_chip=None,
            score=state.score + branch_score,
            first_action=first_action,
        )

    def _projection_for(self, frame: pd.DataFrame) -> dict[int, float]:
        key = id(frame)
        if key not in self._projection_cache:
            self._projection_cache[key] = _projection_map(frame)
        return self._projection_cache[key]


def generate_transfer_options(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    bank: float,
    free_transfers: int,
    max_options: int = 8,
    future_predictions: dict[int, pd.DataFrame] | None = None,
    ranking_mode: str = "current_gw",
) -> list[TransferDecision]:
    """Generate deterministic no-transfer and legal one-transfer branches."""

    if predictions.empty:
        return [_empty_transfer_decision()]
    if ranking_mode not in HIT_POLICIES:
        raise ValueError(f"ranking_mode must be one of {', '.join(HIT_POLICIES)}")
    projection = _projection_map(predictions)
    candidates = predictions.copy()
    if "decision_price" not in candidates:
        candidates["decision_price"] = candidates["price"]
    squad_ids = {int(value) for value in squad["player_id"]}
    team_counts = squad.groupby(squad["team"].astype(str))["player_id"].size().to_dict()
    hit_cost = 0 if free_transfers > 0 else 4
    options: list[tuple[float, int, int, TransferDecision]] = []
    for outgoing in squad.itertuples(index=False):
        outgoing_id = int(outgoing.player_id)
        outgoing_group = position_group(outgoing.position)
        remaining = dict(team_counts)
        outgoing_team = str(outgoing.team)
        remaining[outgoing_team] = remaining.get(outgoing_team, 0) - 1
        for incoming in candidates.itertuples(index=False):
            incoming_id = int(incoming.player_id)
            if incoming_id in squad_ids or position_group(incoming.position) != outgoing_group:
                continue
            incoming_price = float(
                incoming.decision_price
                if pd.notna(incoming.decision_price)
                else incoming.price
            )
            if incoming_price > float(outgoing.price) + bank + 1e-9:
                continue
            if remaining.get(str(incoming.team), 0) >= MAX_PLAYERS_PER_TEAM:
                continue
            projected_gain = projection.get(incoming_id, 0.0) - projection.get(outgoing_id, 0.0)
            decision = TransferDecision(
                outgoing_id=outgoing_id,
                incoming_id=incoming_id,
                outgoing_name=str(outgoing.player_name),
                incoming_name=str(incoming.player_name),
                projected_gain=float(projected_gain),
                net_projected_gain=float(projected_gain - hit_cost),
                hit_cost=hit_cost,
                outgoing_price=float(outgoing.price),
                incoming_price=incoming_price,
            )
            options.append(
                (decision.net_projected_gain, -incoming_id, -outgoing_id, decision)
            )
    if ranking_mode == "horizon_value" and future_predictions:
        # Horizon valuation is much more expensive than legal candidate
        # generation. Keep a deterministic immediate-value shortlist before
        # evaluating full-XI/captain value across future Gameweeks.
        options.sort(key=lambda value: value[:3], reverse=True)
        shortlist = options[: max_options * 3]
        rescored: list[tuple[float, int, int, TransferDecision]] = []
        for _, incoming_key, outgoing_key, decision in shortlist:
            after_transfer = _apply_transfer(squad, predictions, decision)
            horizon_net_gain = (
                _transfer_horizon_gain(
                    squad,
                    after_transfer,
                    projection,
                    future_predictions,
                )
                - hit_cost
            )
            rescored.append((horizon_net_gain, incoming_key, outgoing_key, decision))
        options = rescored
    options.sort(key=lambda value: value[:3], reverse=True)
    return [_empty_transfer_decision(), *(value[3] for value in options[:max_options])]


def _apply_transfer(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    decision: TransferDecision,
) -> pd.DataFrame:
    if not decision.made:
        return squad.copy()
    incoming = predictions[predictions["player_id"] == decision.incoming_id].iloc[0].copy()
    incoming["price"] = decision.incoming_price
    updated = pd.concat(
        [squad[squad["player_id"] != decision.outgoing_id], pd.DataFrame([incoming])],
        ignore_index=True,
    )
    violations = validate_squad(updated, budget=float("inf"))
    if violations:
        raise ValueError("Beam transfer produced an invalid squad: " + "; ".join(violations))
    return updated


def _transfer_horizon_gain(
    before_squad: pd.DataFrame,
    after_squad: pd.DataFrame,
    current_projection: dict[int, float],
    future_predictions: dict[int, pd.DataFrame],
) -> float:
    """Estimate the full-XI/captain value of a transfer over available horizons."""

    gain = _fast_gameweek_value(after_squad, current_projection)[0] - _fast_gameweek_value(
        before_squad, current_projection
    )[0]
    for frame in future_predictions.values():
        projection = _projection_map(frame)
        gain += _fast_gameweek_value(after_squad, projection)[0] - _fast_gameweek_value(
            before_squad, projection
        )[0]
    return float(gain)


def _captain_ids(
    starting_ids: tuple[int, ...], projections: dict[int, float]
) -> tuple[int | None, int | None]:
    ordered = sorted(
        starting_ids,
        key=lambda player_id: (projections.get(player_id, 0.0), -player_id),
        reverse=True,
    )
    return (ordered[0] if ordered else None, ordered[1] if len(ordered) > 1 else None)


def _fast_lineup(squad: pd.DataFrame, projections: dict[int, float]) -> _FastLineup:
    """Evaluate legal formations without repeated DataFrame sorting."""

    pools: dict[str, list[int]] = {}
    position_by_id: dict[int, str] = {}
    squad_ids: list[int] = []
    for row in squad.itertuples(index=False):
        player_id = int(row.player_id)
        position = position_group(row.position)
        position_by_id[player_id] = position
        squad_ids.append(player_id)
    for position in ("GK", "DEF", "MID", "FWD"):
        pools[position] = sorted(
            (player_id for player_id in squad_ids if position_by_id[player_id] == position),
            key=lambda player_id: (-projections.get(player_id, 0.0), player_id),
        )
    best: tuple[float, tuple[int, ...], tuple[int, int, int]] | None = None
    for formation in VALID_FORMATIONS:
        selected = (
            pools["GK"][:1]
            + pools["DEF"][: formation[0]]
            + pools["MID"][: formation[1]]
            + pools["FWD"][: formation[2]]
        )
        if len(selected) != 11:
            continue
        score = float(sum(projections.get(player_id, 0.0) for player_id in selected))
        key = (score, tuple(-player_id for player_id in selected), formation)
        if best is None or key > best:
            best = key
    if best is None:
        raise ValueError("Could not construct a legal beam starting XI")
    _, selected_key, formation = best
    starting_ids = tuple(-player_id for player_id in selected_key)
    starting_set = set(starting_ids)
    bench = [player_id for player_id in squad_ids if player_id not in starting_set]
    position_rank = {"GK": 1, "DEF": 0, "MID": 0, "FWD": 0}
    bench.sort(
        key=lambda player_id: (
            position_rank.get(position_by_id[player_id], 0),
            -projections.get(player_id, 0.0),
            player_id,
        )
    )
    return _FastLineup(starting_ids, tuple(bench), "-".join(str(value) for value in formation))


def _fast_gameweek_value(
    squad: pd.DataFrame,
    projections: dict[int, float],
) -> tuple[float, _FastLineup, float, float]:
    lineup = _fast_lineup(squad, projections)
    starter_points = float(
        sum(projections.get(player_id, 0.0) for player_id in lineup.starting_ids)
    )
    captain = max(
        (float(projections.get(player_id, 0.0)) for player_id in lineup.starting_ids),
        default=0.0,
    )
    bench = float(sum(projections.get(player_id, 0.0) for player_id in lineup.bench_ids))
    return starter_points + captain, lineup, captain, bench


def _fast_uncertainty_penalty(
    squad: pd.DataFrame,
    predictions: pd.DataFrame,
    lineup: _FastLineup,
    *,
    include_bench: bool,
) -> float:
    projection = _projection_map(predictions)
    probabilities = (
        predictions.drop_duplicates("player_id")
        .set_index("player_id")
        .get("probability_60_plus_minutes", pd.Series(dtype=float))
    )
    ids = lineup.starting_ids + (lineup.bench_ids if include_bench else ())
    return float(
        sum(
            max(0.0, projection.get(player_id, 0.0))
            * max(0.0, 1.0 - float(probabilities.get(player_id, 1.0)))
            * 0.05
            for player_id in ids
        )
    )


def _empty_transfer_decision() -> TransferDecision:
    return TransferDecision(None, None, None, None, 0.0, 0.0, 0, None, None)


def _branch_reason(transfer: TransferDecision, chip: ChipDefinition | None) -> str:
    chip_name = chip.name if chip is not None else "no chip"
    transfer_name = "transfer" if transfer.made else "bank transfer"
    return f"beam branch: {chip_name} + {transfer_name}"


def _state_sort_key(state: DecisionState) -> tuple[Any, ...]:
    squad_signature = tuple(sorted(int(value) for value in state.squad["player_id"]))
    first = state.first_action
    first_chip = first.chip.key if first is not None and first.chip is not None else "none"
    first_transfer = first.transfer.incoming_id if first is not None else None
    return (-round(state.score, 8), squad_signature, first_chip, first_transfer or -1)


def _deduplicate_actions(actions: list[BeamAction]) -> tuple[BeamAction, ...]:
    """Keep the strongest legal root branch for each chip counterfactual."""

    best: dict[str, BeamAction] = {}
    for action in actions:
        key = action.chip.key if action.chip is not None else "none"
        previous = best.get(key)
        if previous is None or (
            action.search_score,
            -int(action.transfer.incoming_id or 0),
            -int(action.transfer.outgoing_id or 0),
        ) > (
            previous.search_score,
            -int(previous.transfer.incoming_id or 0),
            -int(previous.transfer.outgoing_id or 0),
        ):
            best[key] = action
    return tuple(
        best[key]
        for key in sorted(best, key=lambda value: (value != "none", value))
    )


def _prune_candidates(
    predictions: pd.DataFrame,
    squad: pd.DataFrame,
    *,
    future_predictions: dict[int, pd.DataFrame] | None = None,
    per_position: int = 12,
) -> pd.DataFrame:
    """Keep a small deterministic pool while preserving the current squad."""

    current_ids = set(int(value) for value in squad["player_id"])
    selected = [predictions[predictions["player_id"].isin(current_ids)]]
    future_predictions = future_predictions or {}
    future_score = _future_score_by_player(future_predictions)
    for position in ("GK", "DEF", "MID", "FWD"):
        pool = predictions[predictions["position"].map(position_group) == position].copy()
        current_pool = pool.sort_values(
            ["expected_points_adjusted", "player_id"],
            ascending=[False, True],
        ).head(per_position)
        selected.append(current_pool)
        if future_score:
            pool["future_expected_points"] = pool["player_id"].map(future_score).fillna(0.0)
            future_pool = pool.sort_values(
                ["future_expected_points", "player_id"],
                ascending=[False, True],
            ).head(per_position)
            selected.append(future_pool.drop(columns=["future_expected_points"]))
        if "selected_by_percent" in pool:
            ownership_pool = pool.sort_values(
                ["selected_by_percent", "player_id"],
                ascending=[False, True],
            ).head(max(2, per_position // 3))
            selected.append(ownership_pool)
    return pd.concat(selected, ignore_index=True).drop_duplicates("player_id")


def _aggregate_horizon_predictions(
    predictions: pd.DataFrame,
    future_predictions: dict[int, pd.DataFrame],
    *,
    minimum_gameweeks: int,
) -> pd.DataFrame:
    """Attach a deterministic multi-Gameweek objective for permanent chips."""

    frames = [predictions, *[frame for _, frame in sorted(future_predictions.items())]]
    frames = frames[:minimum_gameweeks]
    output = predictions.copy()
    totals = pd.Series(0.0, index=output["player_id"])
    for frame in frames:
        values = pd.to_numeric(frame["expected_points_adjusted"], errors="coerce").fillna(0.0)
        by_player = pd.Series(values.to_numpy(), index=frame["player_id"].to_numpy())
        totals = totals.add(by_player, fill_value=0.0)
    output["expected_points_adjusted"] = output["player_id"].map(totals).fillna(0.0)
    return output


def _future_score_by_player(
    future_predictions: dict[int, pd.DataFrame],
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for frame in future_predictions.values():
        if frame.empty or not {
            "player_id",
            "expected_points_adjusted",
        }.issubset(frame.columns):
            continue
        for row in frame[["player_id", "expected_points_adjusted"]].itertuples(index=False):
            player_id = int(row.player_id)
            scores[player_id] = scores.get(player_id, 0.0) + float(
                row.expected_points_adjusted or 0.0
            )
    return scores


def _future_opportunity_cost(
    chip_state: ChipState,
    *,
    chip: ChipDefinition | None,
    future: dict[int, pd.DataFrame],
    retained_squad: pd.DataFrame,
    rules: SeasonRules,
    current_expected_gain: float,
    bank_if_saved: float = 0.0,
    next_chip_state: ChipState | None = None,
) -> float:
    """Compare using a chip now with saving that exact chip for a later deadline."""

    if chip is None or not future or chip.key not in chip_state.remaining:
        return 0.0
    best_future_gain = 0.0
    future_items = sorted(future.items())[:6]
    for index, (gameweek, frame) in enumerate(future_items):
        legal_keys = {
            option.key for option in legal_chip_options(chip_state, gameweek, rules)
        }
        if chip.key not in legal_keys or frame.empty:
            continue
        projection = _projection_map(frame)
        no_chip_value, _, captain, bench = _fast_gameweek_value(
            retained_squad,
            projection,
        )
        following = dict(future_items[index + 1 :])
        if chip.name == "bboost":
            gain = bench
        elif chip.name == "3xc":
            gain = captain
        elif chip.name == "freehit":
            gain = _future_free_hit_gain(
                retained_squad,
                frame,
                projection=projection,
                budget=float(retained_squad["price"].sum()) + bank_if_saved,
                no_chip_value=no_chip_value,
            )
        elif chip.name == "wildcard":
            gain = _future_wildcard_gain(
                retained_squad,
                frame,
                following,
                budget=float(retained_squad["price"].sum()) + bank_if_saved,
            )
        elif chip.name == "assistant_manager":
            gain = _assistant_manager_expected_points(frame) or 0.0
        else:
            gain = 0.0
        best_future_gain = max(best_future_gain, gain)
    return round(max(0.0, best_future_gain - current_expected_gain), 4)


def _future_free_hit_gain(
    retained_squad: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    projection: dict[int, float],
    budget: float,
    no_chip_value: float,
) -> float:
    """Return the one-Gameweek squad gain from saving Free Hit for this frame."""

    try:
        candidates = _prune_candidates(predictions, retained_squad)
        free_hit_squad = build_chip_squad(candidates, budget=budget)
    except ValueError:
        return 0.0
    free_hit_value = _fast_gameweek_value(free_hit_squad, projection)[0]
    return max(0.0, free_hit_value - no_chip_value)


def _future_wildcard_gain(
    retained_squad: pd.DataFrame,
    predictions: pd.DataFrame,
    future_predictions: dict[int, pd.DataFrame],
    *,
    budget: float,
) -> float:
    """Return the permanent squad gain from a future Wildcard horizon."""

    horizon_future = dict(sorted(future_predictions.items())[:5])
    try:
        candidates = _prune_candidates(
            predictions,
            retained_squad,
            future_predictions=horizon_future,
        )
        aggregated = _aggregate_horizon_predictions(
            candidates,
            horizon_future,
            minimum_gameweeks=6,
        )
        wildcard_squad = build_chip_squad(aggregated, budget=budget)
    except ValueError:
        return 0.0
    frames = [predictions, *horizon_future.values()]
    wildcard_value = sum(
        _fast_gameweek_value(wildcard_squad, _projection_map(frame))[0]
        for frame in frames
    )
    retained_value = sum(
        _fast_gameweek_value(retained_squad, _projection_map(frame))[0]
        for frame in frames
    )
    return max(0.0, wildcard_value - retained_value)
