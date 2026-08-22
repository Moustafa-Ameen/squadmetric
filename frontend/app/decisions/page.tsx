"use client";

import { ArrowRight, Banknote, CalendarClock, CheckCircle2, Crown, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getDecisionCenter, getSeasonState } from "@/lib/api";
import { persistDecisionResponse, persistWeeklyRecommendation } from "@/lib/accountStorage";
import { decisionHeadline, formatChip, recommendationIsComplete } from "@/lib/decisionCenter";
import { points, positionCode } from "@/lib/format";
import type {
  DecisionCenterAlternative,
  DecisionCenterPlayer,
  DecisionCenterResponse,
  SeasonState,
} from "@/lib/types";

type Horizon = 3 | 5 | 8;

export default function DecisionCenterPage() {
  const [teamId, setTeamId] = useState("");
  const [horizon, setHorizon] = useState<Horizon>(3);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [data, setData] = useState<DecisionCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [responseStatus, setResponseStatus] = useState<"" | "accepted" | "rejected" | "saving">("");

  useEffect(() => {
    let cancelled = false;
    const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    queueMicrotask(() => {
      setTeamId(savedTeamId);
      setLoading(true);
      setError(false);
    });
    getSeasonState()
      .then(async (state) => {
        if (cancelled) return;
        setSeasonState(state);
        if (!state.recommendations_ready || !savedTeamId) return;
        const response = await getDecisionCenter(savedTeamId, horizon);
        if (!cancelled) setData(response);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [horizon]);

  useEffect(() => {
    if (data?.status === "ready" && data.recommendation) {
      void persistWeeklyRecommendation(data).catch(() => undefined);
    }
  }, [data]);

  async function saveResponse(response: "accepted" | "rejected") {
    if (!data || responseStatus === "saving") return;
    setResponseStatus("saving");
    try {
      await persistDecisionResponse(data, response);
      setResponseStatus(response);
    } catch {
      setResponseStatus("");
    }
  }

  const recommendation = data?.recommendation;
  const playersById = useMemo(
    () => new Map(
      [...(recommendation?.starting_xi ?? []), ...(recommendation?.bench_order ?? [])]
        .map((player) => [player.element_id, player]),
    ),
    [recommendation],
  );

  if (loading) return <PlannerSkeleton />;
  if (error) return <ErrorState />;
  if (!teamId) {
    return (
      <div className="space-y-5">
        <SectionHeader title="This Week" subtitle="One complete recommendation for your next deadline" />
        <Panel>
          <h2 className="text-lg font-semibold text-primary">Connect your FPL Team ID</h2>
          <p className="mt-2 text-sm leading-6 text-secondary">
            Save your Team ID in the sidebar. The decision center will then evaluate your actual
            squad, bank, free transfers, chips, captaincy, bench, and legal hit options together.
          </p>
        </Panel>
      </div>
    );
  }
  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="This Week" subtitle={`Team #${teamId} · recommendations paused`} />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }
  if (!data || data.status !== "ready" || !recommendation || !recommendationIsComplete(recommendation)) {
    return (
      <div className="space-y-5">
        <SectionHeader title="This Week" subtitle={`Team #${teamId}`} />
        <div className="rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 p-5 text-sm leading-6 text-secondary">
          {data?.message ?? "A complete, legal weekly recommendation is not available yet."}
        </div>
      </div>
    );
  }

  const captain = playersById.get(recommendation.captain_id ?? -1);
  const vice = playersById.get(recommendation.vice_captain_id ?? -1);
  const deadline = formatDate(data.deadline);

  return (
    <div className="space-y-5">
      <SectionHeader
        title={`GW${data.gameweek} Decision Center`}
        subtitle={`Team #${teamId} · one synchronized transfer, lineup, captaincy, and chip decision`}
      />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.13em] text-fpl-green">
              <CheckCircle2 className="h-4 w-4" /> Complete legal recommendation
            </div>
            <h2 className="mt-3 text-2xl font-semibold text-primary">{decisionHeadline(recommendation)}</h2>
            <p className="mt-3 text-sm leading-6 text-secondary">{recommendation.reason}</p>
          </div>
          <div className="space-y-2">
            <div className={`rounded-xl border px-5 py-4 text-right ${confidenceStyle(recommendation.confidence)}`}>
              <div className="text-[10px] font-bold uppercase tracking-[0.12em]">Confidence</div>
              <div className="mt-1 text-xl font-semibold capitalize">{recommendation.confidence}</div>
              <div className="mt-1 text-[10px] opacity-75">branch margin {recommendation.confidence_basis.search_score_margin.toFixed(2)}</div>
            </div>
            <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
              {([3, 5, 8] as Horizon[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setHorizon(option)}
                  className={`flex-1 rounded-md px-2 py-1 text-[10px] font-semibold ${horizon === option ? "bg-fpl-green text-fpl-dark" : "text-secondary"}`}
                >
                  {option} GW
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Expected GW points" value={`${points(recommendation.expected_gameweek_points)} pts`} />
          <Metric label={`${data.horizon}-GW total`} value={`${points(recommendation.expected_horizon_points)} pts`} />
          <Metric label="Gain vs do nothing" value={`${signed(recommendation.gain_vs_no_action)} pts`} good={recommendation.gain_vs_no_action > 0} />
          <Metric label="Decision range" value={`${recommendation.downside_range.low.toFixed(1)}–${recommendation.downside_range.high.toFixed(1)}`} />
          <Metric label="Future opportunity cost" value={`${points(recommendation.future_opportunity_cost)} pts`} />
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-secondary">
          <Pill icon={<CalendarClock className="h-3.5 w-3.5" />} text={deadline ? `Deadline ${deadline}` : "Deadline unavailable"} />
          <Pill icon={<Banknote className="h-3.5 w-3.5" />} text={`Bank £${(data.state_before?.bank ?? 0).toFixed(1)}m`} />
          <Pill icon={<Sparkles className="h-3.5 w-3.5" />} text={`${data.state_before?.free_transfers ?? 0} free transfer${data.state_before?.free_transfers === 1 ? "" : "s"}`} />
          <Pill icon={<ShieldCheck className="h-3.5 w-3.5" />} text={`Chip: ${recommendation.chip_action === "save" ? "save" : formatChip(recommendation.chip_action)}`} />
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Panel>
          <h2 className="text-base font-semibold text-primary">Transfer and hit decision</h2>
          {recommendation.transfers.length ? (
            <div className="mt-4 space-y-3">
              {recommendation.transfers.map((transfer, index) => (
                <div key={`${transfer.outgoing_id}-${transfer.incoming_id}-${index}`} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg border border-fpl-border bg-fpl-raised p-4">
                  <div><div className="text-[10px] font-bold uppercase tracking-wide text-fpl-red">Out</div><div className="mt-1 font-semibold text-primary">{transfer.outgoing_name}</div></div>
                  <ArrowRight className="h-5 w-5 text-muted" />
                  <div className="text-right"><div className="text-[10px] font-bold uppercase tracking-wide text-fpl-green">In</div><div className="mt-1 font-semibold text-primary">{transfer.incoming_name}</div></div>
                </div>
              ))}
              <div className={`rounded-lg border p-3 text-sm ${recommendation.hit_recommended ? "border-fpl-amber/30 bg-fpl-amber/10 text-fpl-amber" : "border-fpl-green/30 bg-fpl-green/10 text-fpl-green"}`}>
                {recommendation.hit_recommended
                  ? `The optimizer recommends paying a -${recommendation.hit_cost}; that cost is already included in the decision score.`
                  : "No points hit is recommended."}
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-lg border border-fpl-green/30 bg-fpl-green/10 p-4 text-sm text-secondary">
              Roll the free transfer. Waiting for more information is valued above every legal move currently available.
            </div>
          )}
        </Panel>

        <Panel>
          <div className="flex items-center gap-2"><Crown className="h-5 w-5 text-fpl-gold" /><h2 className="text-base font-semibold text-primary">Captaincy</h2></div>
          <CaptainRow label="Captain" player={captain} expectedMultiplier={2} />
          <CaptainRow label="Vice-captain" player={vice} expectedMultiplier={1} />
          <div className="mt-4 rounded-lg border border-fpl-border bg-fpl-raised p-3 text-xs leading-5 text-muted">
            Vice-captain fallback is selected from the same legal XI and projection state.
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <SquadPanel title="Recommended starting XI" players={recommendation.starting_xi} captainId={recommendation.captain_id} viceCaptainId={recommendation.vice_captain_id} />
        <SquadPanel title="Autosub bench order" players={recommendation.bench_order} captainId={null} viceCaptainId={null} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel>
          <h2 className="text-base font-semibold text-primary">Why not do nothing?</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Metric label="No-action GW" value={`${points(data.no_action?.expected_gameweek_points ?? 0)} pts`} />
            <Metric label={`No-action ${data.horizon}-GW`} value={`${points(data.no_action?.expected_horizon_points ?? 0)} pts`} />
          </div>
          <p className="mt-4 text-sm leading-6 text-secondary">{data.no_action?.reason}</p>
        </Panel>
        <Panel>
          <h2 className="text-base font-semibold text-primary">Best alternatives considered</h2>
          <div className="mt-4 space-y-2">
            {(data.alternatives ?? []).slice(0, 3).map((alternative, index) => (
              <AlternativeRow key={alternative.branch_id} alternative={alternative} rank={index + 2} />
            ))}
          </div>
        </Panel>
      </div>

      <Panel>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-base font-semibold text-primary">Save your decision</h2>
            <p className="mt-1 text-sm text-secondary">Record whether you plan to follow this recommendation. SquadMetric never performs the FPL action for you.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => saveResponse("accepted")} disabled={responseStatus === "saving"} className="fpl-button px-4 py-2 text-sm">
              {responseStatus === "accepted" ? "Plan saved ✓" : "Save as my plan"}
            </button>
            <button type="button" onClick={() => saveResponse("rejected")} disabled={responseStatus === "saving"} className="fpl-secondary-button px-4 py-2 text-sm">
              {responseStatus === "rejected" ? "Not following ✓" : "I’m not following this"}
            </button>
          </div>
        </div>
      </Panel>

      <div className="flex flex-wrap justify-between gap-2 text-[11px] text-muted">
        <span>{data.portfolio_version} · {data.decision_engine_version} · rules {data.rules_version}</span>
        <span>Data cutoff {formatDate(data.data_cutoff) ?? "unavailable"} · {data.bootstrap_hash?.slice(0, 10)}</span>
      </div>
    </div>
  );
}

function SquadPanel({ title, players, captainId, viceCaptainId }: { title: string; players: DecisionCenterPlayer[]; captainId: number | null; viceCaptainId: number | null }) {
  return <Panel><h2 className="text-base font-semibold text-primary">{title}</h2><div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{players.map((player, index) => <div key={player.element_id} className="rounded-lg border border-fpl-border bg-fpl-raised p-3"><div className="flex items-start justify-between gap-2"><span className="font-semibold text-primary">{index + 1}. {player.web_name ?? player.name}{player.element_id === captainId ? " (C)" : player.element_id === viceCaptainId ? " (VC)" : ""}</span><span className="font-mono text-xs text-fpl-green">{points(player.expected_points)}</span></div><div className="mt-1 text-[11px] text-muted">{player.team} · {positionCode(player.position)} · {Math.round(player.start_likelihood * 100)}% start{player.blank ? " · blank" : player.double ? " · double" : ""}</div></div>)}</div></Panel>;
}

function CaptainRow({ label, player, expectedMultiplier }: { label: string; player?: DecisionCenterPlayer; expectedMultiplier: number }) {
  return <div className="mt-4 rounded-lg border border-fpl-border bg-fpl-raised p-4"><div className="text-[10px] font-bold uppercase tracking-wide text-muted">{label}</div><div className="mt-2 flex items-end justify-between gap-3"><div><div className="font-semibold text-primary">{player?.web_name ?? player?.name ?? "-"}</div><div className="mt-1 text-xs text-muted">{player?.team ?? ""} · {Math.round((player?.start_likelihood ?? 0) * 100)}% start</div></div><div className="font-mono text-lg font-bold text-fpl-gold">{points((player?.expected_points ?? 0) * expectedMultiplier)}</div></div></div>;
}

function AlternativeRow({ alternative, rank }: { alternative: DecisionCenterAlternative; rank: number }) {
  const label = alternative.transfers.length ? alternative.transfers.map((move) => `${move.outgoing_name} → ${move.incoming_name}`).join(", ") : "Roll transfer";
  return <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3"><div className="flex justify-between gap-3"><div><div className="text-[10px] font-bold uppercase tracking-wide text-muted">#{rank} · {alternative.chip === "save" ? "save chip" : formatChip(alternative.chip)}</div><div className="mt-1 text-sm font-semibold text-primary">{label}</div></div><div className={`font-mono text-sm ${alternative.gain_vs_no_action > 0 ? "text-fpl-green" : "text-secondary"}`}>{signed(alternative.gain_vs_no_action)}</div></div></div>;
}

function Metric({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3"><div className="text-[10px] uppercase tracking-[0.08em] text-muted">{label}</div><div className={`mt-1 font-mono text-base font-bold ${good ? "text-fpl-green" : "text-primary"}`}>{value}</div></div>;
}

function Pill({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <span className="inline-flex items-center gap-1.5 rounded-full border border-fpl-border bg-fpl-raised px-3 py-1.5">{icon}{text}</span>;
}

function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatDate(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function confidenceStyle(value: "low" | "medium" | "high"): string {
  if (value === "high") return "border-fpl-green/40 bg-fpl-green/10 text-fpl-green";
  if (value === "medium") return "border-fpl-amber/40 bg-fpl-amber/10 text-fpl-amber";
  return "border-fpl-red/40 bg-fpl-red/10 text-fpl-red";
}
