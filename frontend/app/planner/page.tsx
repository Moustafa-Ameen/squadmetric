"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getInitialSquad, getPlanner, getSeasonState } from "@/lib/api";
import { points, positionCode } from "@/lib/format";
import type {
  InitialSquadResponse,
  PlannerPlayer,
  PlannerProjection,
  PlannerResponse,
  SeasonState,
} from "@/lib/types";

type Horizon = 3 | 5 | 8;
type RiskProfile = "maximum_points" | "balanced" | "safe";
type StagedMove = { gameweek: number; outgoingId: number; incomingId: number };
type RosterEntry = { player: PlannerPlayer; starter: boolean; pickOrder: number };
type Roster = Map<number, RosterEntry>;

interface SimulationRow {
  gameweek: number;
  baseline: number;
  projected: number;
  net: number;
  delta: number;
  hit: number;
  blankCount: number;
  doubleCount: number;
  move?: StagedMove;
  valid: boolean;
  message?: string;
  stateBefore: { roster: Roster; bank: number; freeTransfers: number };
  bankAfter: number;
  freeTransfersAfter: number;
}

export default function PlannerPage() {
  const [horizon, setHorizon] = useState<Horizon>(8);
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [teamId, setTeamId] = useState("");
  const [data, setData] = useState<PlannerResponse | null>(null);
  const [initialSquad, setInitialSquad] = useState<InitialSquadResponse | null>(null);
  const [stagedMoves, setStagedMoves] = useState<StagedMove[]>([]);
  const [selectedGameweek, setSelectedGameweek] = useState<number | null>(null);
  const [outgoingId, setOutgoingId] = useState("");
  const [incomingId, setIncomingId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);

  useEffect(() => {
    const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    queueMicrotask(() => {
      setTeamId(savedTeamId);
      setLoading(true);
      setError(false);
    });
    getSeasonState()
      .then(async (state) => {
        setSeasonState(state);
        if (!state.recommendations_ready) return;
        if (savedTeamId) {
          const response = await getPlanner(savedTeamId, horizon);
          setData(response);
          setSelectedGameweek(response.start_gameweek);
          setStagedMoves([]);
          setOutgoingId("");
          setIncomingId("");
        } else {
          setInitialSquad(await getInitialSquad(horizon, riskProfile));
        }
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [horizon, riskProfile]);

  const simulation = useMemo(
    () => (data && data.season_state === "in_season" ? simulatePlan(data, stagedMoves) : []),
    [data, stagedMoves],
  );
  const selectedRow = simulation.find((row) => row.gameweek === selectedGameweek);
  const selectedOutgoing = selectedRow?.stateBefore.roster.get(Number(outgoingId));
  const candidates = useMemo(() => {
    if (!selectedRow || !selectedOutgoing || !data || data.season_state !== "in_season") return [];
    return data.player_pool
      .filter(
        (player) =>
          positionCode(player.position) === positionCode(selectedOutgoing.player.position) &&
          !selectedRow.stateBefore.roster.has(player.element_id),
      )
      .sort(
        (a, b) =>
          averageProjection(b, data.start_gameweek, data.horizon) -
          averageProjection(a, data.start_gameweek, data.horizon),
      );
  }, [data, selectedOutgoing, selectedRow]);

  if (loading) return <PlannerSkeleton />;

  if (error) return <ErrorState />;

  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Transfer Planner" subtitle="Planning is paused until current data passes validation" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }

  if (!teamId && initialSquad) {
    return (
      <div className="space-y-5">
        <SectionHeader
          title={`${initialSquad.season} Initial Squad`}
          subtitle="A legal £100m opening squad using current official prices and fixtures"
        />
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.12em] text-fpl-green">
                Pre-season optimizer
              </div>
              <h2 className="mt-2 text-[20px] font-semibold text-primary">
                {initialSquad.formation} · {money(initialSquad.cost)}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary">
                {initialSquad.assumption}
              </p>
            </div>
            <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
              {([3, 5, 8] as Horizon[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setHorizon(option)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                    horizon === option ? "bg-fpl-green text-fpl-dark" : "text-secondary"
                  }`}
                >
                  {option} GWs
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Info label="Expected GW1 incl. captain" value={`${points(initialSquad.expected_gw1_points)} pts`} />
            <Info label="Captain" value={initialSquadLabel(initialSquad, initialSquad.captain_id)} />
            <Info label="Vice-captain" value={initialSquadLabel(initialSquad, initialSquad.vice_captain_id)} />
          </div>
          {horizon === 8 ? (
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {initialSquad.decision_alternatives.map((alternative) => (
                <button
                  key={alternative.profile}
                  type="button"
                  onClick={() => setRiskProfile(alternative.profile)}
                  className={`rounded-lg border p-3 text-left ${
                    alternative.selected
                      ? "border-fpl-green bg-fpl-green/10"
                      : "border-fpl-border bg-fpl-raised"
                  }`}
                >
                  <span className="text-xs font-semibold uppercase tracking-wide text-secondary">
                    {profileLabel(alternative.profile)}
                  </span>
                  <span className="mt-1 block font-mono text-sm text-primary">
                    {points(alternative.expected_gw1_points)} GW1 xP
                  </span>
                  <span className="mt-1 block text-xs text-secondary">
                    Bench reliability {Math.round(alternative.outfield_bench_start_probability * 100)}%
                  </span>
                </button>
              ))}
            </div>
          ) : null}
          {initialSquad.decision_audit.low_reliability_bench.length > 0 ? (
            <div className="mt-4 rounded-lg border border-fpl-gold/40 bg-fpl-gold/10 p-3 text-xs leading-5 text-secondary">
              <span className="font-semibold text-primary">Bench risk:</span>{" "}
              {initialSquad.decision_audit.low_reliability_bench.join(", ")} currently fall below
              35% starting likelihood. Compare the safer-depth profile and refresh after final team news.
            </div>
          ) : null}
          {initialSquad.deadline_finalization ? (
            <div
              className={`mt-4 rounded-lg border p-3 text-xs leading-5 ${
                initialSquad.deadline_finalization.lock_ready
                  ? "border-fpl-green/40 bg-fpl-green/10"
                  : "border-fpl-gold/40 bg-fpl-gold/10"
              }`}
            >
              <span className="font-semibold text-primary">
                {initialSquad.deadline_finalization.lock_ready
                  ? "Deadline-ready:"
                  : "Deadline monitoring:"}
              </span>{" "}
              {initialSquad.deadline_finalization.lock_ready
                ? "Official data and final-news checks are complete."
                : "The squad is the current leader, but remains preliminary until the final 24-hour refresh and official team-news review."}
              {initialSquad.deadline_finalization.primary_challenger ? (
                <span className="mt-1 block text-secondary">
                  Main challenger ({Math.round(initialSquad.deadline_finalization.primary_challenger.scenario_rate * 100)}%):{" "}
                  {initialSquad.deadline_finalization.primary_challenger.players_out.join(" + ")} →{" "}
                  {initialSquad.deadline_finalization.primary_challenger.players_in.join(" + ")}.
                </span>
              ) : null}
            </div>
          ) : null}
        </Panel>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Panel>
            <h2 className="text-[16px] font-semibold text-primary">Starting XI</h2>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {initialSquad.squad.filter((player) => player.is_starter).map((player) => (
                <InitialPlayer key={player.element_id} player={player} />
              ))}
            </div>
          </Panel>
          <Panel>
            <h2 className="text-[16px] font-semibold text-primary">Bench order</h2>
            <div className="mt-4 space-y-2">
              {initialSquad.squad.filter((player) => !player.is_starter).map((player) => (
                <InitialPlayer key={player.element_id} player={player} />
              ))}
            </div>
            <Link href="/settings" className="mt-5 inline-flex fpl-button px-4 py-2 text-sm">
              Connect my FPL team
            </Link>
          </Panel>
        </div>
        <p className="text-[11px] text-muted">
          {initialSquad.model} · {initialSquad.portfolio_version} · cutoff {initialSquad.data_cutoff}
        </p>
      </div>
    );
  }

  if (!data) return <ErrorState />;

  if (data.season_state !== "in_season") {
    return (
      <div className="space-y-5">
        <SectionHeader
          title="2026/27 Transfer Planner"
          subtitle="Official prices, players, rules and fixtures are loaded"
        />
        <Panel>
          <h2 className="text-[18px] font-semibold text-primary">Pre-season squad access</h2>
          <p className="mt-2 text-sm leading-6 text-secondary">{data.message}</p>
          {data.decision_error ? (
            <p className="mt-3 rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 p-3 text-sm text-fpl-amber">
              {data.decision_error}
            </p>
          ) : null}
        </Panel>
      </div>
    );
  }

  const selectedIncoming = data.player_pool.find((player) => player.element_id === Number(incomingId));
  const budgetLimit = selectedOutgoing
    ? roundMoney((selectedRow?.stateBefore.bank ?? 0) + selectedOutgoing.player.price)
    : 0;
  const incomingTooExpensive = Boolean(selectedIncoming && selectedIncoming.price > budgetLimit + 0.001);
  const summary = simulation.reduce(
    (result, row) => ({
      baseline: result.baseline + row.baseline,
      net: result.net + row.net,
      hit: result.hit + row.hit,
    }),
    { baseline: 0, net: 0, hit: 0 },
  );

  function stageTransfer() {
    if (!selectedGameweek || !selectedOutgoing || !selectedIncoming || incomingTooExpensive) return;
    setStagedMoves((current) => [
      ...current.filter((move) => move.gameweek !== selectedGameweek),
      { gameweek: selectedGameweek, outgoingId: selectedOutgoing.player.element_id, incomingId: selectedIncoming.element_id },
    ].sort((a, b) => a.gameweek - b.gameweek));
    setOutgoingId("");
    setIncomingId("");
  }

  function selectGameweek(gameweek: number) {
    setSelectedGameweek(gameweek);
    setOutgoingId("");
    setIncomingId("");
  }

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Transfer Planner"
        subtitle={`Plan ${horizon} gameweeks ahead for Team #${teamId}`}
      />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-fpl-green">
              Complete optimizer recommendation
            </div>
            {data.decision ? (
              <>
                <h2 className="mt-2 text-[20px] font-semibold text-primary">
                  {data.decision.transfer_count > 0
                    ? `${data.decision.transfer_count} transfer${data.decision.transfer_count === 1 ? "" : "s"}`
                    : "Roll the transfer"}
                  {data.decision.total_hit_cost > 0
                    ? ` · -${data.decision.total_hit_cost} hit`
                    : ""}
                </h2>
                {data.decision.transfers.length > 0 ? (
                  <div className="mt-2 space-y-1 text-sm text-primary">
                    {data.decision.transfers.map((move) => (
                      <div key={`${move.outgoing_id}-${move.incoming_id}`}>
                        {move.outgoing_name} → {move.incoming_name}
                      </div>
                    ))}
                  </div>
                ) : null}
                <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary">
                  {data.decision.reason}
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm text-fpl-amber">
                {data.decision_error ?? "No complete recommendation is available."}
              </p>
            )}
          </div>
          <div className="rounded-lg border border-fpl-border bg-fpl-raised px-4 py-3 text-right">
            <div className="text-xs text-muted">Recommended chip</div>
            <div className="mt-1 font-semibold text-primary">{data.decision?.chip ?? "Save"}</div>
          </div>
        </div>
        {data.decision ? (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Info label="Expected GW points" value={points(data.decision.expected_gameweek_points)} />
              <Info label={`${horizon}-GW projection`} value={points(data.decision.expected_horizon_points)} />
              <Info
                label="Horizon gain"
                value={`${data.decision.expected_horizon_gain >= 0 ? "+" : ""}${points(data.decision.expected_horizon_gain)}`}
              />
              <Info
                label="Captain / vice"
                value={`${playerLabel(data, data.decision.captain_id)} / ${playerLabel(data, data.decision.vice_captain_id)}`}
              />
            </div>
            <p className="mt-3 text-[11px] text-muted">
              Portfolio {data.portfolio_version ?? "unknown"} · transfer {data.transfer_model ?? data.model} ·
              captain {data.captain_model ?? "unknown"} · chip {data.chip_model ?? "unknown"}
            </p>
          </>
        ) : null}
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-[18px] font-semibold text-primary">Build your own transfer plan</h2>
            <p className="mt-1 max-w-2xl text-[13px] text-secondary">
              Stage one hypothetical move per gameweek and watch it carry forward through the horizon.
              Nothing is selected automatically.
            </p>
          </div>
          <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
            {([3, 5, 8] as Horizon[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setHorizon(option)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                  horizon === option ? "bg-fpl-green text-fpl-dark" : "text-secondary hover:text-primary"
                }`}
              >
                {option} GWs
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-muted">
          <span className="rounded-full border border-fpl-border bg-fpl-raised px-2.5 py-1">Model: {data.model}</span>
          <span className="rounded-full border border-fpl-border bg-fpl-raised px-2.5 py-1">Bank: {money(data.bank_value)}</span>
          <span className="rounded-full border border-fpl-border bg-fpl-raised px-2.5 py-1">
            Free transfers: {data.free_transfers_available}
          </span>
        </div>
        <p className="mt-3 text-xs text-muted">{data.assumption}</p>
      </Panel>

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="No-change projection" value={`${points(summary.baseline)} pts`} />
        <Metric label="Your staged plan" value={`${points(summary.net)} pts`} accent={summary.net >= summary.baseline} />
        <Metric label="Planned hit cost" value={summary.hit ? `-${summary.hit} pts` : "0 pts"} danger={summary.hit > 0} />
      </div>

      <Panel>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-[16px] font-semibold text-primary">Gameweek timeline</h2>
            <p className="mt-1 text-xs text-muted">Select a GW to stage a move. Totals are starting XI projections.</p>
          </div>
          <div className="hidden text-xs text-muted md:block">Starting from GW{data.start_gameweek}</div>
        </div>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {simulation.map((row) => (
            <button
              key={row.gameweek}
              type="button"
              onClick={() => selectGameweek(row.gameweek)}
              className={`rounded-lg border p-3 text-left ${
                row.gameweek === selectedGameweek
                  ? "border-fpl-green bg-fpl-green/10"
                  : "border-fpl-border bg-fpl-raised hover:border-fpl-green/40"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-bold text-primary">GW{row.gameweek}</span>
                {row.move ? <span className="h-2 w-2 rounded-full bg-fpl-green" /> : null}
              </div>
              <div className="mt-3 font-mono text-xl font-bold text-primary">{points(row.net)}</div>
              <div className="mt-1 text-[11px] text-muted">
                Baseline {points(row.baseline)}
                {row.hit ? <span className="ml-2 text-fpl-red">-{row.hit} hit</span> : null}
              </div>
              <div className="mt-2 text-[10px] text-muted">
                Bank {money(row.bankAfter)} · Next FT {row.freeTransfersAfter}
              </div>
              {row.blankCount || row.doubleCount ? (
                <div className="mt-2 flex flex-wrap gap-1 text-[10px] font-semibold uppercase tracking-[0.06em]">
                  {row.blankCount ? <span className="rounded border border-fpl-amber/30 px-1.5 py-0.5 text-fpl-amber">{row.blankCount} blank</span> : null}
                  {row.doubleCount ? <span className="rounded border border-fpl-green/30 px-1.5 py-0.5 text-fpl-green">{row.doubleCount} double</span> : null}
                </div>
              ) : null}
              <div className={`mt-2 text-xs font-semibold ${row.delta >= 0 ? "text-fpl-green" : "text-fpl-red"}`}>
                {row.delta >= 0 ? "+" : ""}{points(row.delta)} vs baseline
              </div>
              <div className="mt-2 flex gap-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                {row.gameweek === selectedGameweek ? <span className="text-fpl-green">Selected</span> : null}
                {row.message ? <span className="text-fpl-red">Check move</span> : null}
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_350px]">
        <Panel>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-primary">Stage a transfer</h2>
              <p className="mt-1 text-xs text-secondary">Selected GW{selectedGameweek ?? data.start_gameweek} changes the plan from that point onward.</p>
            </div>
            {selectedRow?.move ? (
              <button
                type="button"
                onClick={() => setStagedMoves((moves) => moves.filter((move) => move.gameweek !== selectedRow.gameweek))}
                className="inline-flex items-center gap-1 text-xs font-semibold text-fpl-red hover:text-primary"
              >
                <X className="h-3.5 w-3.5" /> Remove move
              </button>
            ) : null}
          </div>

          <div className="grid gap-3 md:grid-cols-[1fr_36px_1fr] md:items-end">
            <label className="block text-xs font-semibold text-muted">
              OUT
              <select
                value={outgoingId}
                onChange={(event) => { setOutgoingId(event.target.value); setIncomingId(""); }}
                className="mt-2 w-full rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2.5 text-sm text-primary outline-none focus:border-fpl-green"
              >
                <option value="">Choose a squad player</option>
                {selectedRow ? Array.from(selectedRow.stateBefore.roster.values()).map(({ player, starter }) => (
                  <option key={player.element_id} value={player.element_id}>
                    {starter ? "XI" : "Bench"} · {player.name} · {money(player.price)}
                  </option>
                )) : null}
              </select>
            </label>
            <ArrowRight className="mx-auto mb-2 hidden h-5 w-5 text-muted md:block" />
            <label className="block text-xs font-semibold text-muted">
              IN
              <select
                value={incomingId}
                onChange={(event) => setIncomingId(event.target.value)}
                disabled={!selectedOutgoing}
                className="mt-2 w-full rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2.5 text-sm text-primary outline-none focus:border-fpl-green disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">Choose a replacement</option>
                {candidates.map((candidate) => (
                  <option
                    key={candidate.element_id}
                    value={candidate.element_id}
                    disabled={candidate.price > budgetLimit + 0.001}
                  >
                    {candidate.name} · {money(candidate.price)}
                    {candidate.price > budgetLimit + 0.001 ? " · over budget" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="mt-4 grid gap-2 text-xs sm:grid-cols-3">
            <Info label="Available budget" value={selectedOutgoing ? money(budgetLimit) : "Choose OUT first"} />
            <Info label="Free transfers before GW" value={selectedRow ? String(selectedRow.stateBefore.freeTransfers) : "-"} />
            <Info label="Transfer cost" value={selectedRow?.stateBefore.freeTransfers ? "1 free transfer" : "-4 hit"} />
          </div>
          {incomingTooExpensive ? (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-fpl-red/30 bg-fpl-red/10 p-3 text-xs text-fpl-red">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              This player costs more than the outgoing price plus your bank. Choose a cheaper replacement or a different OUT.
            </div>
          ) : null}
          <button
            type="button"
            onClick={stageTransfer}
            disabled={!selectedOutgoing || !selectedIncoming || incomingTooExpensive}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-fpl-green px-4 py-2.5 text-sm font-bold text-fpl-dark disabled:cursor-not-allowed disabled:opacity-40"
          >
            Stage move <ArrowRight className="h-4 w-4" />
          </button>
        </Panel>

        <Panel>
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-primary">Staged moves</h2>
              <p className="mt-1 text-xs text-muted">Moves carry forward until replaced.</p>
            </div>
            <RotateCcw className="h-4 w-4 text-muted" />
          </div>
          <div className="mt-4 space-y-2">
            {stagedMoves.length ? stagedMoves.map((move) => {
              const outgoing = data.player_pool.find((player) => player.element_id === move.outgoingId) ?? data.squad.find((player) => player.element_id === move.outgoingId);
              const incoming = data.player_pool.find((player) => player.element_id === move.incomingId);
              const row = simulation.find((item) => item.gameweek === move.gameweek);
              return (
                <div key={move.gameweek} className="rounded-lg border border-fpl-border bg-fpl-raised p-3">
                  <div className="flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                    <span>GW{move.gameweek}</span>
                    {row?.hit ? <span className="text-fpl-red">-{row.hit} hit</span> : <span className="text-fpl-green">Free transfer</span>}
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-sm">
                    <span className="truncate text-fpl-red">{outgoing?.name ?? "Unknown"}</span>
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted" />
                    <span className="truncate font-semibold text-fpl-green">{incoming?.name ?? "Unknown"}</span>
                  </div>
                  {row?.message ? <div className="mt-2 text-xs text-fpl-red">{row.message}</div> : null}
                </div>
              );
            }) : <p className="rounded-lg border border-dashed border-fpl-border p-4 text-sm text-muted">No moves staged yet.</p>}
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-muted">
            This planner uses current prices for affordability. FPL selling value can differ after price rises.
          </p>
        </Panel>
      </div>
    </div>
  );
}

function simulatePlan(data: PlannerResponse, moves: StagedMove[]): SimulationRow[] {
  const playerById = new Map<number, PlannerPlayer>([
    ...data.player_pool.map((player) => [player.element_id, player] as const),
    ...data.squad.map((player) => [player.element_id, player] as const),
  ]);
  const roster = new Map<number, RosterEntry>(
    data.squad.map((player) => [player.element_id, {
      player,
      starter: Boolean(player.is_starter),
      pickOrder: player.pick_order ?? 99,
    }]),
  );
  let bank = roundMoney(data.bank_value ?? 0);
  let freeTransfers = Math.max(0, data.free_transfers_available ?? 0);
  const rows: SimulationRow[] = [];

  for (const baseline of data.baseline) {
    const stateBefore = {
      roster: new Map(roster),
      bank,
      freeTransfers,
    };
    const move = moves.find((item) => item.gameweek === baseline.gameweek);
    let valid = true;
    let message: string | undefined;
    let hit = 0;

    if (move) {
      const outgoing = roster.get(move.outgoingId);
      const incoming = playerById.get(move.incomingId);
      if (!outgoing || !incoming) {
        valid = false;
        message = "Player is no longer in the simulated squad.";
      } else if (roster.has(move.incomingId)) {
        valid = false;
        message = "Incoming player is already in the simulated squad.";
      } else if (positionCode(outgoing.player.position) !== positionCode(incoming.position)) {
        valid = false;
        message = "FPL transfers must replace like-for-like positions.";
      } else if (incoming.price > bank + outgoing.player.price + 0.001) {
        valid = false;
        message = "Incoming player is over the available budget.";
      } else {
        hit = freeTransfers > 0 ? 0 : 4;
        bank = roundMoney(bank + outgoing.player.price - incoming.price);
        roster.delete(move.outgoingId);
        roster.set(move.incomingId, {
          player: incoming,
          starter: outgoing.starter,
          pickOrder: outgoing.pickOrder,
        });
      }
    }

    const projected = totalProjection(roster, baseline.gameweek);
    const net = projected - hit;
    rows.push({
      gameweek: baseline.gameweek,
      baseline: baseline.projected_points,
      projected,
      net,
      delta: net - baseline.projected_points,
      hit,
      blankCount: baseline.blank_count,
      doubleCount: baseline.double_count,
      move,
      valid,
      message,
      stateBefore,
      bankAfter: bank,
      freeTransfersAfter: freeTransfers,
    });

    if (move && valid && freeTransfers > 0) freeTransfers -= 1;
    freeTransfers = Math.min(data.max_extra_free_transfers, freeTransfers + 1);
  }

  return rows;
}

function totalProjection(roster: Roster, gameweek: number): number {
  return roundMoney(
    Array.from(roster.values())
      .filter((entry) => entry.starter)
      .reduce((sum, entry) => sum + projectionFor(entry.player, gameweek).projected_points, 0),
  );
}

function projectionFor(player: PlannerPlayer, gameweek: number): PlannerProjection {
  return player.projections.find((projection) => projection.gameweek === gameweek) ?? {
    gameweek,
    projected_points: 0,
    blank: true,
    double: false,
    fixtures: [],
  };
}

function averageProjection(player: PlannerPlayer, startGameweek: number, horizon: number): number {
  return player.projections
    .filter((projection) => projection.gameweek >= startGameweek && projection.gameweek < startGameweek + horizon)
    .reduce((sum, projection) => sum + projection.projected_points, 0);
}

function roundMoney(value: number): number {
  return Math.round(value * 10) / 10;
}

function money(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : `\u00a3${value.toFixed(1)}m`;
}

function playerLabel(data: PlannerResponse, elementId: number | null): string {
  if (elementId === null) return "-";
  return (
    data.squad.find((player) => player.element_id === elementId)?.web_name ??
    data.player_pool.find((player) => player.element_id === elementId)?.web_name ??
    `#${elementId}`
  );
}

function initialSquadLabel(data: InitialSquadResponse, elementId: number): string {
  return (
    data.squad.find((player) => player.element_id === elementId)?.web_name ??
    `#${elementId}`
  );
}

function profileLabel(profile: RiskProfile): string {
  if (profile === "maximum_points") return "Maximum points";
  if (profile === "safe") return "Safer depth";
  return "Balanced";
}

function InitialPlayer({
  player,
}: {
  player: InitialSquadResponse["squad"][number];
}) {
  return (
    <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-primary">
            {player.web_name ?? player.player_name}
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {player.team} · {positionCode(player.position)} · {money(player.price)}
          </div>
        </div>
        <div className="font-mono text-sm font-bold text-fpl-green">
          {points(player.gw1_points)}
        </div>
      </div>
      <div className="mt-2 text-[10px] text-muted">
        {player.horizon_points.toFixed(1)} pts over selected horizon
        {player.start_likelihood !== undefined
          ? ` · ${Math.round(player.start_likelihood * 100)}% start likelihood`
          : ""}
      </div>
      {player.robustness_class ? (
        <div className="mt-2 text-[10px] font-semibold uppercase tracking-wide text-secondary">
          {player.robustness_class} · {Math.round((player.scenario_selection_rate ?? 0) * 100)}% of scenarios
        </div>
      ) : null}
      {player.set_piece &&
      (player.set_piece.penalties_rank !== null ||
        player.set_piece.direct_free_kicks_rank !== null ||
        player.set_piece.corners_indirect_rank !== null) ? (
        <div className="mt-2 text-[10px] text-secondary">
          {[
            player.set_piece.penalties_rank !== null
              ? `Pens #${player.set_piece.penalties_rank}`
              : null,
            player.set_piece.direct_free_kicks_rank !== null
              ? `Direct FK #${player.set_piece.direct_free_kicks_rank}`
              : null,
            player.set_piece.corners_indirect_rank !== null
              ? `Corners #${player.set_piece.corners_indirect_rank}`
              : null,
          ]
            .filter(Boolean)
            .join(" · ")}
          {Math.abs(player.set_piece.transition_adjustment_per_start) >= 0.01
            ? ` · ${player.set_piece.transition_adjustment_per_start > 0 ? "+" : ""}${player.set_piece.transition_adjustment_per_start.toFixed(2)} role xP/start`
            : ""}
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value, accent, danger }: { label: string; value: string; accent?: boolean; danger?: boolean }) {
  return (
    <div className="fpl-card-shadow rounded-lg border border-fpl-border bg-fpl-card p-4">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</div>
      <div className={`mt-3 font-mono text-xl font-bold ${danger ? "text-fpl-red" : accent ? "text-fpl-green" : "text-primary"}`}>{value}</div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3">
      <div className="text-[10px] uppercase tracking-[0.08em] text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-primary">{value}</div>
    </div>
  );
}
