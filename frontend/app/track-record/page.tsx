"use client";

import { ArrowRight, CalendarX, CheckCircle2, Scale, ShieldAlert, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorState, TableSkeleton } from "@/components/LoadingState";
import { SectionHeader } from "@/components/SectionHeader";
import { getTrackRecord } from "@/lib/api";
import type { TrackRecordGameweek, TrackRecordResponse } from "@/lib/types";

export default function TrackRecordPage() {
  const [record, setRecord] = useState<TrackRecordResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getTrackRecord().then(setRecord).catch(() => setError(true));
  }, []);

  if (error) return <ErrorState />;
  if (!record) return <TableSkeleton />;

  const { totals } = record;
  const gameweeks = [...record.gameweeks].sort((a, b) => b.gameweek - a.gameweek);
  const total = totals.total_gain_vs_no_action ?? 0;
  const fromChips = totals.total_gain_from_chips ?? 0;

  return (
    <div className="space-y-7">
      <SectionHeader title="Track record" subtitle="Every saved SquadMetric plan, scored with official FPL points once the gameweek is final." />

      {totals.scored ? (
        <section className="overflow-hidden rounded-3xl border border-violet-200 bg-[linear-gradient(135deg,#ffffff_0%,#f3f0ff_65%,#ecfdf5_100%)] p-6 shadow-[0_18px_55px_rgba(76,29,149,0.09)] sm:p-8">
          <div className="text-xs font-bold uppercase tracking-[0.15em] text-violet-700">2026/27 so far</div>
          <h2 className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950 sm:text-4xl">
            <span className={gainClass(total)}>{signed(total)} points</span> versus doing nothing
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
            Across {totals.scored} scored {totals.scored === 1 ? "gameweek" : "gameweeks"}, following the plan would have scored {signed(total)} points more than keeping the same squad.
            {fromChips ? ` ${signed(fromChips)} of that came from chips.` : ""}
          </p>
        </section>
      ) : (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8">
          <h2 className="text-2xl font-black tracking-[-0.03em] text-slate-950">No gameweeks scored yet</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">Plans are saved before every deadline and scored once official results are final.</p>
        </section>
      )}

      {totals.scored ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={CheckCircle2} label="Gameweeks scored" value={String(totals.scored)} detail="Plans saved before the deadline" />
          <StatCard icon={TrendingUp} label="Ahead · level · behind" value={`${totals.weeks_ahead ?? 0} · ${totals.weeks_level ?? 0} · ${totals.weeks_behind ?? 0}`} detail="Weeks versus doing nothing" />
          <StatCard icon={Scale} label="Average per gameweek" value={`${signed(totals.average_gain_vs_no_action ?? 0)} pts`} detail="Gain versus doing nothing" />
          <StatCard icon={ShieldAlert} label="Gain from chips" value={`${signed(fromChips)} pts`} detail={`${signed(round(total - fromChips))} pts from transfers and lineup`} />
        </div>
      ) : null}

      {gameweeks.length ? (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6">
          <div className="mb-5"><h2 className="text-xl font-black text-slate-950">Gameweek by gameweek</h2><p className="mt-1 text-sm text-slate-600">What SquadMetric recommended before the deadline, and what it actually scored.</p></div>
          <div className="space-y-3">{gameweeks.map((row) => <GameweekRow key={row.gameweek} row={row} />)}</div>
        </section>
      ) : null}

      {record.unscored_gameweeks.length ? (
        <section className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
          <CalendarX className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
          <div>
            <div className="font-black">Not scored: {record.unscored_gameweeks.map((gw) => `GW${gw}`).join(", ")}</div>
            <p className="mt-1 text-amber-900">No plan was saved before those deadlines, and a plan made afterwards could not be scored honestly. A plan is now saved automatically before every deadline.</p>
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Note good title="How each gameweek is scored" items={[
          "Before the deadline, SquadMetric saves its recommended plan and every alternative it considered.",
          "After official scores are final, each saved plan is scored with real points, including any points hit.",
          "The comparison is the same squad with no transfers and no chip.",
        ]} />
        <Note title="What to keep in mind" items={[
          "Plans are made for one real FPL team, and scored whether or not that manager followed them.",
          "Each gameweek is scored on its own. A chip recommended in two weeks counts twice here, though it can only be played once.",
          "A handful of gameweeks is a small sample in a high-variance game.",
        ]} />
      </div>
    </div>
  );
}

function GameweekRow({ row }: { row: TrackRecordGameweek }) {
  const { recommendation } = row;
  const moves = recommendation.transfers.length
    ? recommendation.transfers.map((move) => `${move.out} → ${move.in}`).join(", ")
    : "No transfer";
  return (
    <article className="grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-[72px_minmax(0,1fr)_auto] sm:items-center">
      <div className="text-lg font-black text-slate-950">GW{row.gameweek}</div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-950">
          <span className="inline-flex items-center gap-1">{moves}</span>
          {recommendation.hit_cost ? <Badge tone="rose">−{recommendation.hit_cost} hit</Badge> : null}
          {recommendation.chip ? <Badge tone="violet">{recommendation.chip}</Badge> : null}
        </div>
        <div className="mt-1 text-xs leading-5 text-slate-500">
          Captain {recommendation.captain ?? "—"} · {row.options_considered} options considered · best option scored {fmt(row.best_option_points)}
        </div>
      </div>
      <div className="flex items-center gap-3 sm:justify-end">
        <div className="text-right text-xs leading-5 text-slate-500">
          <div><span className="font-bold text-slate-900">{fmt(row.recommended_points)}</span> plan</div>
          <div><span className="font-bold text-slate-900">{fmt(row.no_action_points)}</span> no change</div>
        </div>
        <ArrowRight className="h-4 w-4 text-slate-300" aria-hidden="true" />
        <div className="min-w-20 text-right">
          <div className={`text-xl font-black ${gainClass(row.gain_vs_no_action)}`}>{signed(row.gain_vs_no_action)}</div>
          {row.chip_gain ? <div className="text-[11px] font-semibold text-slate-500">{signed(row.chip_gain)} from chip</div> : null}
        </div>
      </div>
    </article>
  );
}

function StatCard({ icon: Icon, label, value, detail }: { icon: typeof TrendingUp; label: string; value: string; detail: string }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)]"><Icon className="h-5 w-5 text-violet-600" /><div className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-500">{label}</div><div className="mt-1 text-2xl font-black text-slate-950">{value}</div><div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div></div>;
}

function Badge({ tone, children }: { tone: "rose" | "violet"; children: React.ReactNode }) {
  const colors = tone === "rose" ? "border-rose-200 bg-rose-50 text-rose-700" : "border-violet-200 bg-violet-50 text-violet-700";
  return <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${colors}`}>{children}</span>;
}

function Note({ good = false, title, items }: { good?: boolean; title: string; items: string[] }) {
  return <section className={`rounded-2xl border p-5 ${good ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}><div className={`flex items-center gap-2 font-black ${good ? "text-emerald-950" : "text-amber-950"}`}>{good ? <CheckCircle2 className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}{title}</div><ul className={`mt-3 space-y-2 text-sm leading-6 ${good ? "text-emerald-900" : "text-amber-900"}`}>{items.map((item) => <li key={item} className="flex gap-2"><span aria-hidden="true">•</span><span>{item}</span></li>)}</ul></section>;
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

function fmt(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function signed(value: number): string {
  if (value > 0) return `+${fmt(value)}`;
  if (value < 0) return `−${fmt(Math.abs(value))}`;
  return "0";
}

function gainClass(value: number): string {
  if (value > 0) return "text-emerald-700";
  if (value < 0) return "text-rose-700";
  return "text-slate-700";
}
