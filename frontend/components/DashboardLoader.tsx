"use client";

import Link from "next/link";
import { ArrowRight, CalendarClock, RefreshCw, ShieldCheck, Users, UserRoundSearch } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getDecisionCenter, getOverview, getSeasonState } from "@/lib/api";
import type { DecisionCenterResponse, OverviewResponse, SeasonState } from "@/lib/types";
import { DashboardClient } from "./DashboardClient";
import { DashboardSkeleton } from "./LoadingState";

export function DashboardLoader() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [overviewError, setOverviewError] = useState(false);
  const [seasonError, setSeasonError] = useState(false);
  const [decisionCenter, setDecisionCenter] = useState<DecisionCenterResponse | null>(null);
  const [teamId, setTeamId] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const linkedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    setTeamId(linkedTeamId);
    const [overviewResult, seasonResult, decisionResult] = await Promise.allSettled([
      getOverview(),
      getSeasonState(),
      linkedTeamId ? getDecisionCenter(linkedTeamId, 3) : Promise.resolve(null),
    ]);
    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
      setOverviewError(false);
    } else {
      setOverview(null);
      setOverviewError(true);
    }
    if (seasonResult.status === "fulfilled") {
      setSeasonState(seasonResult.value);
      setSeasonError(false);
    } else {
      setSeasonState(null);
      setSeasonError(true);
    }
    setDecisionCenter(decisionResult.status === "fulfilled" ? decisionResult.value : null);
    setLoading(false);
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  if (loading && !overview && !seasonState && !overviewError) return <DashboardSkeleton />;
  if (overviewError || !overview || seasonState?.recommendations_ready === false) {
    return <DashboardRefreshState seasonState={seasonState} loading={loading} onRefresh={load} />;
  }

  return <DashboardClient overview={overview} seasonState={seasonState} seasonStateUnavailable={seasonError} decisionCenter={decisionCenter} teamId={teamId} />;
}

function DashboardRefreshState({
  seasonState,
  loading,
  onRefresh,
}: {
  seasonState: SeasonState | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
}) {
  const gameweek = seasonState?.next_gw ?? seasonState?.current_gw ?? 1;
  const age = seasonState?.artifact_data.age_hours;

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.15em] text-violet-700">Gameweek {gameweek}</div>
          <h1 className="mt-2 text-3xl font-black tracking-[-0.04em] text-slate-950 sm:text-4xl">Your decision dashboard</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Your team and planning tools remain available while recommendations are paused.</p>
        </div>
        <button type="button" onClick={() => void onRefresh()} disabled={loading} className="sm-secondary-button self-start px-4 py-2.5 sm:self-auto">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Checking…" : "Check again"}
        </button>
      </section>

      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-slate-900 to-violet-950 p-6 text-white shadow-[0_22px_60px_rgba(15,23,42,0.18)] sm:p-8" role="status">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.15em] text-amber-300"><RefreshCw className="h-4 w-4" />Manual refresh required</div>
            <h2 className="mt-3 text-2xl font-black tracking-[-0.035em] sm:text-3xl">Recommendations are paused until the data bundle is refreshed.</h2>
            <p className="mt-3 text-sm leading-6 text-slate-300">SquadMetric withholds transfer, captain and chip calls when a finalized gameweek is missing. It will not update data automatically; run the manual refresh, then use “Check again”.</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.07] px-5 py-4 lg:min-w-64">
            <div className="flex items-center gap-2 text-sm font-bold text-emerald-300"><ShieldCheck className="h-5 w-5" />Your account is safe</div>
            <div className="mt-2 text-xs leading-5 text-slate-300">Saved team, preferences and drafts are unaffected.</div>
            {typeof age === "number" ? <div className="mt-3 text-xs font-semibold text-slate-400">Last validated snapshot: {age.toFixed(1)}h ago</div> : null}
          </div>
        </div>
      </section>

      <section>
        <div className="text-xs font-bold uppercase tracking-[0.15em] text-violet-700">Available now</div>
        <h2 className="mt-2 text-2xl font-black tracking-[-0.03em] text-slate-950">Keep planning while recommendations are paused</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <RefreshLink href="/squad" title="My Team" detail="Review your current XI and bench." icon={<Users className="h-5 w-5" />} />
          <RefreshLink href="/stats" title="Players" detail="Browse current official players and prices." icon={<UserRoundSearch className="h-5 w-5" />} />
          <RefreshLink href="/fixtures" title="Fixtures" detail="Check upcoming opponents and schedules." icon={<CalendarClock className="h-5 w-5" />} />
          <RefreshLink href="/deadline" title="Deadline center" detail="Follow final checks and team-news timing." icon={<ShieldCheck className="h-5 w-5" />} />
        </div>
      </section>
    </div>
  );
}

function RefreshLink({ href, title, detail, icon }: { href: string; title: string; detail: string; icon: React.ReactNode }) {
  return (
    <Link href={href} className="group rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-lg">
      <div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-violet-100 text-violet-700">{icon}</span><ArrowRight className="h-4 w-4 text-slate-300 group-hover:text-violet-600" /></div>
      <div className="mt-5 font-bold text-slate-950">{title}</div>
      <div className="mt-1 text-sm leading-5 text-slate-500">{detail}</div>
    </Link>
  );
}
