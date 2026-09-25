"use client";

import Link from "next/link";
import {
  CalendarClock,
  Check,
  ChevronDown,
  Crown,
  ListOrdered,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Target,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getDecisionCenter, getSeasonState } from "@/lib/api";
import { persistWeeklyRecommendation } from "@/lib/accountStorage";
import { recommendationIsComplete } from "@/lib/decisionCenter";
import { points, positionCode } from "@/lib/format";
import {
  clearManagerStateOverride,
  readManagerStateOverride,
  saveManagerStateOverride,
} from "@/lib/managerState";
import type {
  DecisionCenterAlternative,
  DecisionCenterResponse,
  SeasonState,
} from "@/lib/types";

export default function DecisionCenterPage() {
  const [teamId, setTeamId] = useState("");
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [data, setData] = useState<DecisionCenterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showStateEditor, setShowStateEditor] = useState(false);
  const [bankDraft, setBankDraft] = useState("0.0");
  const [freeTransfersDraft, setFreeTransfersDraft] = useState("1");
  const [refreshToken, setRefreshToken] = useState(0);

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
        const response = await getDecisionCenter(
          savedTeamId,
          3,
          readManagerStateOverride(savedTeamId),
        );
        if (!cancelled) {
          setData(response);
          if (response.state_before) {
            setBankDraft(response.state_before.bank.toFixed(1));
            setFreeTransfersDraft(String(response.state_before.free_transfers));
          }
        }
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
  }, [refreshToken]);

  useEffect(() => {
    if (data?.status === "ready" && data.recommendation) {
      void persistWeeklyRecommendation(data).catch(() => undefined);
    }
  }, [data]);

  function applyManagerState() {
    const bank = Number(bankDraft);
    const freeTransfers = Number(freeTransfersDraft);
    if (!Number.isFinite(bank) || bank < 0 || bank > 20) return;
    if (!Number.isInteger(freeTransfers) || freeTransfers < 0 || freeTransfers > 5) return;
    saveManagerStateOverride(teamId, {
      bank: Math.round(bank * 10) / 10,
      freeTransfers,
    });
    setShowStateEditor(false);
    setRefreshToken((value) => value + 1);
  }

  function useReconstructedState() {
    clearManagerStateOverride(teamId);
    setShowStateEditor(false);
    setRefreshToken((value) => value + 1);
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
        <SectionHeader title="This Week" subtitle="Your transfer, captain, and bench order in one place" />
        <Panel>
          <h2 className="text-lg font-extrabold text-slate-950">Connect your FPL team first</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Add your Team ID from My Team so SquadMetric can build a legal plan around your squad and bank.
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
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
          {data?.message ?? "A complete, legal weekly recommendation is not available yet."}
        </div>
      </div>
    );
  }

  const captain = playersById.get(recommendation.captain_id ?? -1);
  const vice = playersById.get(recommendation.vice_captain_id ?? -1);
  const deadline = formatDate(data.deadline);
  const firstBench = recommendation.bench_order.find((player) => positionCode(player.position) !== "GK") ?? recommendation.bench_order[0];
  const futurePlan = recommendation.future_plan ?? [];

  return (
    <div className="space-y-6">
      <SectionHeader title={`This Week · GW${data.gameweek}`} subtitle={`Team #${teamId} · one clear plan for the next deadline`} />

      <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
        <div className="flex flex-col gap-4 border-b border-slate-200 bg-gradient-to-r from-emerald-50 via-white to-violet-50 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <div>
            <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.14em] text-emerald-700">
              <Check className="h-4 w-4" /> Ready for the deadline
            </div>
            <h2 className="mt-2 text-2xl font-black tracking-[-0.03em] text-slate-950">
              {recommendation.transfers.length ? "Make the transfer" : "Bank the transfer"}
              {recommendation.hit_recommended ? ` and take a -${recommendation.hit_cost}` : ""}
            </h2>
            <p className="mt-1 text-sm text-slate-600">{primaryExplanation(recommendation, data.horizon)}</p>
          </div>
          <span className={`w-fit rounded-full px-3 py-1.5 text-xs font-extrabold ${confidenceStyle(recommendation.confidence)}`}>
            {confidenceLabel(recommendation.confidence)} confidence
          </span>
        </div>

        <div className="grid divide-y divide-slate-200 lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <PlanAction
            icon={<RefreshCw className="h-5 w-5" />}
            eyebrow="Transfer"
            title={transferTitle(recommendation)}
            detail={recommendation.hit_recommended ? `Includes a -${recommendation.hit_cost} hit` : "No points hit"}
            tone="violet"
          />
          <PlanAction
            icon={<Crown className="h-5 w-5" />}
            eyebrow="Captain"
            title={captain?.web_name ?? captain?.name ?? "Not available"}
            detail={`Vice-captain: ${vice?.web_name ?? vice?.name ?? "Not available"}`}
            tone="amber"
          />
          <PlanAction
            icon={<ListOrdered className="h-5 w-5" />}
            eyebrow="First substitute"
            title={firstBench?.web_name ?? firstBench?.name ?? "Not available"}
            detail="Best autosub cover from the recommended bench"
            tone="emerald"
          />
        </div>

        <div className="grid gap-3 border-t border-slate-200 bg-slate-50/70 p-4 sm:grid-cols-2 lg:grid-cols-4 lg:px-7">
          <QuickFact label="GW forecast" value={`${points(recommendation.expected_gameweek_points)} pts`} />
          <QuickFact label={`Gain over ${data.horizon} GWs`} value={`${signed(recommendation.gain_vs_no_action)} pts`} positive={recommendation.gain_vs_no_action > 0} />
          <QuickFact label="Available" value={`${data.state_before?.free_transfers ?? 0} free transfer${data.state_before?.free_transfers === 1 ? "" : "s"}`} />
          <QuickFact label="In the bank" value={`£${(data.state_before?.bank ?? 0).toFixed(1)}m`} />
        </div>
      </section>

      <div className="flex flex-wrap gap-2 text-xs font-semibold text-slate-600">
        <InfoPill icon={<CalendarClock className="h-4 w-4" />} text={deadline ? `Deadline ${deadline}` : "Deadline unavailable"} />
        <InfoPill icon={<Target className="h-4 w-4" />} text={`${data.horizon}-gameweek forecast selected`} />
        <InfoPill icon={<ShieldCheck className="h-4 w-4" />} text="Squad and budget checked" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-600">
            Planning with <strong className="text-slate-950">£{(data.state_before?.bank ?? 0).toFixed(1)}m</strong> in the bank and <strong className="text-slate-950">{data.state_before?.free_transfers ?? 0} free transfer{data.state_before?.free_transfers === 1 ? "" : "s"}</strong>.
            <span className="ml-1 text-xs text-slate-600">
              {data.manager_state_confirmation?.bank_source === "user_override" ? "Confirmed by you." : "Reconstructed from public FPL history."}
            </span>
          </div>
          <button type="button" onClick={() => setShowStateEditor((value) => !value)} className="inline-flex items-center gap-2 text-sm font-extrabold text-violet-700 hover:text-violet-900">
            <Settings2 className="h-4 w-4" /> Correct this
          </button>
        </div>
        {showStateEditor ? (
          <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <label className="text-xs font-bold text-slate-600">
              Money in bank (£m)
              <input type="number" min="0" max="20" step="0.1" value={bankDraft} onChange={(event) => setBankDraft(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold text-slate-950 outline-none focus:border-violet-500" />
            </label>
            <label className="text-xs font-bold text-slate-600">
              Free transfers
              <select value={freeTransfersDraft} onChange={(event) => setFreeTransfersDraft(event.target.value)} className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-950 outline-none focus:border-violet-500">
                {[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <div className="flex gap-2">
              <button type="button" onClick={applyManagerState} className="fpl-button px-4 py-2 text-sm">Recalculate</button>
              {(data.manager_state_confirmation?.bank_source === "user_override" || data.manager_state_confirmation?.free_transfers_source === "user_override") ? (
                <button type="button" onClick={useReconstructedState} className="fpl-secondary-button px-3 py-2 text-sm">Reset</button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {recommendation.transfers.length ? (
        <Panel>
          <h2 className="text-base font-extrabold text-slate-950">Transfer package</h2>
          <div className="mt-4 space-y-3">
            {recommendation.transfers.map((move, index) => (
              <div key={`${move.outgoing_id}-${move.incoming_id}-${index}`} className="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-center">
                <div><div className="text-xs font-bold text-slate-600">SELL</div><div className="font-black text-slate-950">{move.outgoing_name}</div><div className="text-xs text-slate-500">£{(move.outgoing_price ?? 0).toFixed(1)}m</div></div>
                <span className="font-black text-slate-400">→</span>
                <div><div className="text-xs font-bold text-slate-600">BUY</div><div className="font-black text-slate-950">{move.incoming_name}</div><div className="text-xs text-slate-500">£{(move.incoming_price ?? 0).toFixed(1)}m</div></div>
                <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-extrabold ${(move.bank_effect ?? 0) >= 0 ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
                  {(move.bank_effect ?? 0) >= 0 ? "Releases" : "Uses"} £{Math.abs(move.bank_effect ?? 0).toFixed(1)}m
                </span>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-xl bg-violet-50 px-4 py-3 text-sm font-semibold text-violet-950">
            {recommendation.funding_explanation ?? `Bank: £${recommendation.bank_before.toFixed(1)}m → £${recommendation.bank_after.toFixed(1)}m.`}
          </div>
        </Panel>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <Panel className="p-0 sm:p-0">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 sm:px-6">
              <div>
                <h2 className="font-extrabold text-slate-950">Why this plan?</h2>
                <p className="mt-1 text-sm text-slate-500">The useful reasoning, without the model jargon</p>
              </div>
              <ChevronDown className="h-5 w-5 text-slate-400 transition group-open:rotate-180" />
            </summary>
            <div className="border-t border-slate-200 px-5 py-5 sm:px-6">
              <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                {decisionReason(recommendation, data.horizon)}
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <QuickFact label="Do nothing" value={`${points(data.no_action?.expected_horizon_points ?? 0)} pts`} />
                <QuickFact label="Recommended plan" value={`${points(recommendation.expected_horizon_points)} pts`} />
                <QuickFact label="Expected difference" value={`${signed(recommendation.gain_vs_no_action)} pts`} positive={recommendation.gain_vs_no_action > 0} />
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">
                The comparison includes points hits, the value of saving a free transfer, your exact selling prices and money left in the bank. Confirmed injured, suspended or non-playing players are treated as replacement priorities.
              </p>
              {futurePlan.length ? (
                <div className="mt-5 rounded-2xl border border-dashed border-slate-300 p-4">
                  <div className="text-xs font-extrabold uppercase tracking-[0.12em] text-slate-600">Recheck next week</div>
                  <p className="mt-1 text-sm text-slate-600">These are useful directions, not locked-in transfers. SquadMetric recalculates after injuries, prices and the next deadline.</p>
                  <div className="mt-3 space-y-2">
                    {futurePlan.map((step) => (
                      <div key={step.gameweek} className="flex flex-col justify-between gap-1 rounded-xl bg-slate-50 px-3 py-2 text-sm sm:flex-row sm:items-center">
                        <strong className="text-slate-950">GW{step.gameweek}</strong>
                        <span className="text-slate-600">{step.transfers.length ? step.transfers.map((move) => `${move.outgoing_name} → ${move.incoming_name}`).join(", ") : "Currently projects as a roll"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </details>
        </Panel>

        <Panel className="p-0 sm:p-0">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 sm:px-6">
              <div>
                <h2 className="font-extrabold text-slate-950">Other moves considered</h2>
                <p className="mt-1 text-sm text-slate-500">The next-best legal options</p>
              </div>
              <ChevronDown className="h-5 w-5 text-slate-400 transition group-open:rotate-180" />
            </summary>
            <div className="space-y-2 border-t border-slate-200 px-5 py-5 sm:px-6">
              {(data.alternatives ?? []).slice(0, 3).map((alternative, index) => (
                <AlternativeRow key={alternative.branch_id} alternative={alternative} rank={index + 2} />
              ))}
            </div>
          </details>
        </Panel>
      </div>

      <div className="flex flex-col gap-2 border-t border-slate-200 pt-4 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span>Want chip timing rather than a squad-specific chip call?</span>
        <Link href="/chips" className="font-extrabold text-violet-700 hover:text-violet-900">Open the Chip Guide →</Link>
      </div>
    </div>
  );
}

function PlanAction({ icon, eyebrow, title, detail, tone }: { icon: React.ReactNode; eyebrow: string; title: string; detail: string; tone: "violet" | "amber" | "emerald" }) {
  const toneClasses = {
    violet: "bg-violet-100 text-violet-700",
    amber: "bg-amber-100 text-amber-700",
    emerald: "bg-emerald-100 text-emerald-700",
  };
  return (
    <div className="flex gap-4 p-5 sm:p-6">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${toneClasses[tone]}`}>{icon}</span>
      <div className="min-w-0">
        <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600">{eyebrow}</div>
        <div className="mt-1 text-base font-black text-slate-950">{title}</div>
        <div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div>
      </div>
    </div>
  );
}

function QuickFact({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <div className="text-[10px] font-extrabold uppercase tracking-[0.11em] text-slate-600">{label}</div>
      <div className={`mt-1 text-sm font-black ${positive ? "text-emerald-700" : "text-slate-950"}`}>{value}</div>
    </div>
  );
}

function InfoPill({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 shadow-sm">{icon}{text}</span>;
}

function AlternativeRow({ alternative, rank }: { alternative: DecisionCenterAlternative; rank: number }) {
  const label = alternative.transfers.length
    ? alternative.transfers.map((move) => `${move.outgoing_name} → ${move.incoming_name}`).join(", ")
    : "Bank the transfer";
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-slate-600">Option {rank}</div>
          <div className="mt-1 text-sm font-bold text-slate-900">{label}</div>
        </div>
        <div className={`shrink-0 text-sm font-black ${alternative.gain_vs_no_action > 0 ? "text-emerald-700" : "text-slate-500"}`}>
          {signed(alternative.gain_vs_no_action)}
        </div>
      </div>
    </div>
  );
}

function transferTitle(recommendation: NonNullable<DecisionCenterResponse["recommendation"]>): string {
  if (!recommendation.transfers.length) return "Save it for next week";
  if (recommendation.transfers.length > 1) return `${recommendation.transfers.length} linked transfers`;
  return recommendation.transfers
    .map((transfer) => `${transfer.outgoing_name ?? "Player"} → ${transfer.incoming_name ?? "Player"}`)
    .join(", ");
}

function primaryExplanation(recommendation: NonNullable<DecisionCenterResponse["recommendation"]>, horizon: number): string {
  if (recommendation.transfers.length) {
    return `Projected to gain ${signed(recommendation.gain_vs_no_action)} points across the next ${horizon} gameweeks.`;
  }
  return `Keeping the free transfer is worth more than the legal moves currently available across the next ${horizon} gameweeks.`;
}

function decisionReason(recommendation: NonNullable<DecisionCenterResponse["recommendation"]>, horizon: number): string {
  if (!recommendation.transfers.length) {
    return `Keeping the transfer is projected to be more useful than the moves currently available after comparing the next ${horizon} gameweeks, money in the bank and the extra flexibility next week.`;
  }
  const move = transferTitle(recommendation);
  const hit = recommendation.hit_recommended
    ? ` Even after the -${recommendation.hit_cost} cost, it remains the strongest legal plan.`
    : " It uses only your available free transfers, so there is no points deduction.";
  return `${move} is the strongest legal move and projects ${signed(recommendation.gain_vs_no_action)} points more than doing nothing.${hit}`;
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

function confidenceLabel(value: "low" | "medium" | "high"): string {
  if (value === "high") return "High";
  if (value === "medium") return "Balanced";
  return "Close call";
}

function confidenceStyle(value: "low" | "medium" | "high"): string {
  if (value === "high") return "bg-emerald-100 text-emerald-800";
  if (value === "medium") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}
