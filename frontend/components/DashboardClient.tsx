"use client";

import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Crown,
  RefreshCw,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DecisionCenterResponse, OverviewResponse, SeasonState } from "@/lib/types";

export function DashboardClient({ overview, seasonState, seasonStateUnavailable, decisionCenter, teamId }: { overview: OverviewResponse; seasonState: SeasonState | null; seasonStateUnavailable: boolean; decisionCenter: DecisionCenterResponse | null; teamId: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const personalized = teamId && decisionCenter?.status === "ready" ? decisionCenter.recommendation : undefined;
  const genericCaptain = overview.captains[0] ?? overview.predictions[0];
  const topCaptain = personalized?.starting_xi.find((player) => player.element_id === personalized.captain_id) ?? (!teamId ? genericCaptain : undefined);
  const popularAlternative = personalized?.starting_xi.find((player) => player.element_id === personalized.vice_captain_id) ?? (!teamId ? overview.captains[1] ?? overview.predictions[1] : undefined);
  const differential = overview.gems[0];
  const transfer = personalized?.transfers[0];
  const gameweek = seasonState?.next_gw ?? seasonState?.current_gw ?? 1;
  const deadline = formatDeadline(seasonState?.next_season_start, now);
  const projectedPoints = useMemo(() => personalized?.expected_gameweek_points ?? overview.predictions.slice(0, 11).reduce((total, player) => total + (player.expected_points ?? 0), 0), [overview.predictions, personalized]);

  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <PageIntro gameweek={gameweek} />
        <TeamConnection teamId={teamId} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <PageIntro gameweek={gameweek} />
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600"><span className="h-2 w-2 rounded-full bg-emerald-500" />Recommendations current</span>
          <Link href="/deadline" className="sm-secondary-button px-4 py-2.5"><CalendarClock className="h-4 w-4" />Deadline center</Link>
        </div>
      </section>

      <section className="deadline-banner" aria-label={`Gameweek ${gameweek} deadline`}>
        <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/15"><CalendarClock className="h-5 w-5" /></span><div><div className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-200">GW{gameweek} deadline</div><div className="mt-1 text-lg font-bold text-white">{deadline}</div></div></div>
        <div className="text-sm text-slate-300">Final checks: transfers · captain · bench · chips</div>
      </section>

      {seasonStateUnavailable ? <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status"><strong>Freshness status unavailable.</strong> The recommendation data loaded, but confirm the deadline center before acting.</div> : null}
      <TeamConnection teamId={teamId} />

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.55fr)]">
        <article className="overflow-hidden rounded-3xl bg-slate-950 text-white shadow-[0_22px_60px_rgba(15,23,42,0.18)]">
          <div className="border-b border-white/10 px-6 py-5 sm:px-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.15em] text-emerald-300"><Sparkles className="h-4 w-4" />Primary recommendation</div>
              <span className="rounded-full bg-emerald-400/15 px-3 py-1.5 text-xs font-bold capitalize text-emerald-200">{personalized ? `${personalized.confidence} confidence` : teamId ? "Personal plan unavailable" : "Generic scouting view"}</span>
            </div>
          </div>
          <div className="px-6 py-7 sm:px-7 sm:py-8">
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-sm font-semibold text-slate-400">Captain for Gameweek {gameweek}</div>
                <h2 className="mt-2 text-3xl font-black tracking-[-0.035em] sm:text-4xl">{topCaptain ? displayName(topCaptain) : "Recommendation pending"}</h2>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">{personalized?.reason ?? (teamId ? decisionCenter?.message ?? "Open the decision center to retry your personalized plan." : genericCaptain?.reasoning ?? "Generic scouting leader until you link a team.")}</p>
              </div>
              {topCaptain ? <div className="min-w-36 rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-center"><div className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">Expected points</div><div className="mt-2 text-3xl font-black text-emerald-300">{topCaptain.expected_points.toFixed(1)}</div><div className="mt-1 text-xs text-slate-400">{Math.round(topCaptain.start_likelihood * 100)}% start chance</div></div> : null}
            </div>
            <Link href="/captain" className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-emerald-300 hover:text-emerald-200">Review captaincy evidence<ArrowRight className="h-4 w-4" /></Link>
          </div>
        </article>

        <aside className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          <AlternativeCard eyebrow={personalized ? "Vice-captain" : "Scouting alternative"} name={popularAlternative ? displayName(popularAlternative) : "Not available"} detail={popularAlternative ? `${popularAlternative.expected_points.toFixed(1)} xP · ${Math.round(popularAlternative.start_likelihood * 100)}% start chance` : "No squad-relative alternative available"} icon={<Shield className="h-5 w-5" />} tone="violet" />
          <AlternativeCard eyebrow="Generic differential scout" name={differential?.name ?? "Not available"} detail={differential ? `${(differential.selected_by_percent ?? 0).toFixed(1)}% selected · Not a squad recommendation` : "Waiting for a differential"} icon={<TrendingUp className="h-5 w-5" />} tone="amber" />
        </aside>
      </section>

      <section aria-labelledby="weekly-actions-title">
        <div className="flex items-end justify-between gap-4"><div><div className="text-xs font-bold uppercase tracking-[0.15em] text-violet-700">Your checklist</div><h2 id="weekly-actions-title" className="mt-2 text-2xl font-black tracking-[-0.03em] text-slate-950">This gameweek’s decisions</h2></div><Link href="/decisions" className="hidden text-sm font-bold text-violet-700 hover:text-violet-900 sm:inline-flex sm:items-center sm:gap-2">Open full plan<ArrowRight className="h-4 w-4" /></Link></div>
        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ActionCard icon={<RefreshCw className="h-5 w-5" />} label="Transfers" value={transfer ? `${transfer.outgoing_name ?? "Player"} → ${transfer.incoming_name ?? "Player"}` : personalized ? "Roll the transfer" : "No personalized call"} detail={transfer ? `${transfer.projected_gain.toFixed(2)} projected-point gain` : personalized?.transfer_action ?? "Open the decision center"} href="/transfers" />
          <ActionCard icon={<Crown className="h-5 w-5" />} label="Captain" value={topCaptain ? displayName(topCaptain) : "Pending"} detail="Primary pick ready" href="/captain" complete />
          <ActionCard icon={<Users className="h-5 w-5" />} label="Bench" value={teamId ? "Review order" : "Link team first"} detail="Balance upside and autosub cover" href="/squad" />
          <ActionCard icon={<Zap className="h-5 w-5" />} label="Chip" value="Proactive calls paused" detail="Availability remains live while validation builds" href="/chips" />
        </div>
      </section>

      <details className="group rounded-3xl border border-slate-200 bg-white shadow-sm">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 sm:px-6">
          <div><div className="font-bold text-slate-950">Why SquadMetric prefers this plan</div><div className="mt-1 text-sm text-slate-500">Projections, fixtures, uncertainty, and model context</div></div>
          <ChevronDown className="h-5 w-5 text-slate-400 transition group-open:rotate-180" />
        </summary>
        <div className="grid gap-4 border-t border-slate-200 p-5 sm:grid-cols-2 sm:p-6 xl:grid-cols-4">
          <Evidence label="Projected XI" value={`${projectedPoints.toFixed(1)} xP`} detail="Top 11 current projections" icon={<Target className="h-5 w-5" />} />
          <Evidence label="Player pool" value={overview.player_count.toLocaleString()} detail="Players evaluated" icon={<Users className="h-5 w-5" />} />
          <Evidence label="Model error" value={modelError(overview)} detail="Lower is better" icon={<CircleAlert className="h-5 w-5" />} />
          <Evidence label="Data cutoff" value={formatCutoff(overview.data_cutoff)} detail="Recommendation snapshot" icon={<CheckCircle2 className="h-5 w-5" />} />
        </div>
      </details>
    </div>
  );
}

function PageIntro({ gameweek }: { gameweek: number }) { return <div><div className="text-xs font-bold uppercase tracking-[0.15em] text-violet-700">Gameweek {gameweek}</div><h1 className="mt-2 text-3xl font-black tracking-[-0.04em] text-slate-950 sm:text-4xl">Your decision dashboard</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Recommendations first. Supporting analysis when you need it.</p></div>; }

function TeamConnection({ teamId }: { teamId: string }) { return teamId ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3"><div className="flex items-center gap-3 text-sm text-emerald-900"><CheckCircle2 className="h-5 w-5" /><span><strong>Team #{teamId} linked.</strong> Squad-aware pages can personalize your decisions.</span></div><Link href="/settings" className="text-sm font-bold text-emerald-800 hover:text-emerald-950">Manage team</Link></div> : <div className="flex flex-col gap-4 rounded-2xl border border-violet-200 bg-violet-50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-bold text-slate-950">Link your FPL team for personalized decisions</div><div className="mt-1 text-sm text-slate-600">Use your public Team ID or team URL—never your FPL password.</div></div><Link href="/settings" className="sm-primary-button shrink-0 justify-center px-4 py-2.5">Link my team<ArrowRight className="h-4 w-4" /></Link></div>; }

function AlternativeCard({ eyebrow, name, detail, icon, tone }: { eyebrow: string; name: string; detail: string; icon: React.ReactNode; tone: "violet" | "amber" }) { return <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"><div className={`flex h-10 w-10 items-center justify-center rounded-2xl ${tone === "violet" ? "bg-violet-100 text-violet-700" : "bg-amber-100 text-amber-700"}`}>{icon}</div><div className="mt-5 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{eyebrow}</div><div className="mt-2 text-lg font-bold text-slate-950">{name}</div><div className="mt-1 text-sm leading-6 text-slate-500">{detail}</div></article>; }

function ActionCard({ icon, label, value, detail, href, complete = false }: { icon: React.ReactNode; label: string; value: string; detail: string; href: string; complete?: boolean }) { return <Link href={href} className="group rounded-3xl border border-slate-200 bg-white p-5 shadow-sm hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-lg"><div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700 group-hover:bg-violet-100 group-hover:text-violet-700">{icon}</span>{complete ? <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.08em] text-emerald-700">Ready</span> : <ArrowRight className="h-4 w-4 text-slate-300 group-hover:text-violet-600" />}</div><div className="mt-5 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">{label}</div><div className="mt-2 font-bold text-slate-950">{value}</div><div className="mt-1 text-sm leading-5 text-slate-500">{detail}</div></Link>; }

function Evidence({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: React.ReactNode }) { return <div className="rounded-2xl bg-slate-50 p-4"><div className="text-violet-700">{icon}</div><div className="mt-4 text-xs font-bold uppercase tracking-[0.1em] text-slate-500">{label}</div><div className="mt-2 text-xl font-black text-slate-950">{value}</div><div className="mt-1 text-xs text-slate-500">{detail}</div></div>; }

function displayName(player: { name: string; web_name?: string }) { return player.web_name || player.name; }
function modelError(overview: OverviewResponse) { const row = overview.accuracy.find((item) => item.model.toLowerCase().includes("best")) ?? overview.accuracy[0]; return row ? (row.adjusted_MAE ?? row.raw_MAE).toFixed(2) : "—"; }
function formatCutoff(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "Current" : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date); }
function formatDeadline(value: string | null | undefined, now: number) { if (!value) return "Deadline time is syncing"; const deadline = new Date(value); if (Number.isNaN(deadline.getTime())) return "Deadline time is syncing"; const diff = deadline.getTime() - now; if (diff <= 0) return "Deadline passed · awaiting the next update"; const minutes = Math.floor(diff / 60_000); const days = Math.floor(minutes / 1440); const hours = Math.floor((minutes % 1440) / 60); const mins = minutes % 60; return `${days ? `${days}d ` : ""}${hours}h ${mins}m remaining`; }
