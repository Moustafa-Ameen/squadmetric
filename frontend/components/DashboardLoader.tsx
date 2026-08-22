"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getOverview, getSeasonState } from "@/lib/api";
import type { OverviewResponse, SeasonState } from "@/lib/types";
import { DashboardClient } from "./DashboardClient";
import { DashboardSkeleton } from "./LoadingState";

export function DashboardLoader() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [overviewError, setOverviewError] = useState(false);
  const [seasonError, setSeasonError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [overviewResult, seasonResult] = await Promise.allSettled([getOverview(), getSeasonState()]);
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
    setLoading(false);
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  if (loading && !overview) return <DashboardSkeleton />;
  if (overviewError || !overview) {
    return (
      <section className="mx-auto max-w-2xl rounded-3xl border border-rose-200 bg-white p-7 shadow-sm" role="alert">
        <div className="text-xs font-bold uppercase tracking-[0.14em] text-rose-700">Dashboard unavailable</div>
        <h1 className="mt-3 text-2xl font-black tracking-[-0.035em] text-slate-950">We could not load your decision data.</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">The recommendation service may be refreshing. Your saved account information is unaffected.</p>
        <button type="button" onClick={() => void load()} className="sm-primary-button mt-6 px-5 py-3"><RefreshCw className="h-4 w-4" />Retry dashboard</button>
      </section>
    );
  }

  return <DashboardClient overview={overview} seasonState={seasonState} seasonStateUnavailable={seasonError} />;
}
