"use client";

import { CalendarX, Crown, Info, Repeat2, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState, TableSkeleton } from "@/components/LoadingState";
import { getTrackRecord } from "@/lib/api";
import type { TrackRecordGameweek, TrackRecordResponse } from "@/lib/types";

// Validated two-series palette (light surface): transfers & lineup, chips.
const MOVE_COLOR = "#059669";
const CHIP_COLOR = "#8b5cf6";

type TimelineEntry = { key: string; row: TrackRecordGameweek } | { key: string; row: null; from: number; to: number };

export default function TrackRecordPage() {
  const [record, setRecord] = useState<TrackRecordResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getTrackRecord().then(setRecord).catch(() => setError(true));
  }, []);

  const timeline = useMemo<TimelineEntry[]>(() => {
    if (!record) return [];
    // Newest first, with back-to-back unscored gameweeks merged into one row.
    const byGameweek = new Map<number, TrackRecordGameweek | null>();
    record.gameweeks.forEach((row) => byGameweek.set(row.gameweek, row));
    record.unscored_gameweeks.forEach((gameweek) => byGameweek.set(gameweek, null));
    const entries: TimelineEntry[] = [];
    for (const gameweek of [...byGameweek.keys()].sort((a, b) => b - a)) {
      const row = byGameweek.get(gameweek) ?? null;
      const last = entries[entries.length - 1];
      if (row) entries.push({ key: `gw-${gameweek}`, row });
      else if (last && last.row === null && last.from === gameweek + 1) last.from = gameweek;
      else entries.push({ key: `gap-${gameweek}`, row: null, from: gameweek, to: gameweek });
    }
    return entries;
  }, [record]);

  if (error) return <ErrorState />;
  if (!record) return <TableSkeleton />;

  const { totals } = record;
  const total = totals.total_gain_vs_no_action ?? 0;
  const fromChips = totals.total_gain_from_chips ?? 0;
  const fromMoves = round(total - fromChips);
  const currentRows = record.gameweeks.filter((row) => row.current_version);

  return (
    <div className="space-y-6">
      <header>
        <div className="text-xs font-black uppercase tracking-[0.16em] text-violet-700">2026/27 season</div>
        <h1 className="mt-2 text-3xl font-black tracking-[-0.045em] text-slate-950 sm:text-4xl">Track record</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Every plan SquadMetric saved before a deadline, scored with official FPL points once the gameweek was final.</p>
      </header>

      {totals.scored ? (
        <section className="grid overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.10)] lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="border-b border-slate-200 p-6 sm:p-8 lg:border-b-0 lg:border-r">
            <div className="text-xs font-black uppercase tracking-[0.14em] text-slate-500">Current version, versus keeping the same squad</div>
            <div className={`mt-3 text-6xl font-black tracking-[-0.06em] sm:text-7xl ${gainText(total)}`}>{signed(total)}</div>
            <div className="mt-1 text-sm font-semibold text-slate-700">points over {totals.scored} scored {totals.scored === 1 ? "gameweek" : "gameweeks"}</div>

            {fromChips ? (
              <div className="mt-7">
                <div className="flex items-center justify-between text-xs font-bold text-slate-500"><span>Where the points came from</span></div>
                <SplitBar moves={fromMoves} chips={fromChips} />
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <LegendValue color={MOVE_COLOR} label="Transfers & lineup" value={fromMoves} />
                  <LegendValue color={CHIP_COLOR} label="Chips" value={fromChips} />
                </div>
              </div>
            ) : null}

            <div className="mt-7 grid grid-cols-3 gap-2">
              <RecordPill label="Ahead" value={totals.weeks_ahead ?? 0} tone="good" />
              <RecordPill label="Level" value={totals.weeks_level ?? 0} tone="neutral" />
              <RecordPill label="Behind" value={totals.weeks_behind ?? 0} tone="bad" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-violet-50/70 to-white p-6 sm:p-8">
            {currentRows.length >= 2 ? (
              <>
                <div className="text-xs font-black uppercase tracking-[0.14em] text-violet-700">Gain by gameweek</div>
                <div className="mt-3 flex flex-wrap gap-4 text-xs font-semibold text-slate-600">
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: MOVE_COLOR }} />Transfers & lineup</span>
                  <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHIP_COLOR }} />Chip</span>
                </div>
                <GainChart rows={currentRows} />
                <p className="mt-2 text-xs leading-5 text-slate-500">Average {signed(totals.average_gain_vs_no_action ?? 0)} points per scored gameweek.</p>
              </>
            ) : (
              <>
                <div className="text-xs font-black uppercase tracking-[0.14em] text-violet-700">Why so few gameweeks</div>
                <h2 className="mt-3 text-xl font-black tracking-[-0.025em] text-slate-950">This record only counts what SquadMetric recommends today.</h2>
                <p className="mt-3 text-sm leading-6 text-slate-600">The planner was rebuilt during the season and no longer makes chip calls, so results from earlier versions are listed below but left out of the total.</p>
                <p className="mt-3 text-sm leading-6 text-slate-600">A plan is now saved before every deadline, and a chart appears here once there are two gameweeks to compare. That is too little to judge the model yet.</p>
              </>
            )}
          </div>
        </section>
      ) : (
        <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_rgba(15,23,42,0.08)] sm:p-8">
          <h2 className="text-2xl font-black tracking-[-0.03em] text-slate-950">No gameweeks scored yet</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">A plan is saved before every deadline and scored once official results are final. Only the current version of SquadMetric counts here.</p>
        </section>
      )}

      {timeline.length ? (
        <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6">
          <h2 className="text-xl font-black tracking-[-0.02em] text-slate-950">Gameweek by gameweek</h2>
          <p className="mt-1 text-sm text-slate-600">What was recommended before the deadline, and what it scored.</p>
          <ol className="mt-5 space-y-3">
            {timeline.map((entry) => entry.row ? <ScoredRow key={entry.key} row={entry.row} /> : <UnscoredRow key={entry.key} from={entry.from} to={entry.to} />)}
          </ol>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="rounded-[28px] border border-slate-200 bg-white p-5 sm:p-6">
          <div className="flex items-center gap-2 font-black text-slate-950"><ShieldCheck className="h-5 w-5 text-emerald-600" />How each gameweek is scored</div>
          <ol className="mt-4 space-y-4">
            <Step n={1} title="Saved before the deadline" text="The recommended plan and every alternative considered are frozen before the deadline passes." />
            <Step n={2} title="Scored with official points" text="Once FPL marks the gameweek final, each saved plan is scored with real points, including any hit." />
            <Step n={3} title="Compared with no change" text="The baseline is the same squad with no transfers and no chip." />
          </ol>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5 sm:p-6">
          <div className="flex items-center gap-2 font-black text-slate-950"><Info className="h-5 w-5 text-slate-500" />Worth knowing</div>
          <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
            <li>Plans are made for one real FPL team and scored whether or not that manager followed them.</li>
            <li>Earlier-version plans are shown for transparency only. They include chip calls SquadMetric no longer makes.</li>
            <li>A few gameweeks is a small sample in a high-variance game.</li>
          </ul>
        </div>
      </section>
    </div>
  );
}

function SplitBar({ moves, chips }: { moves: number; chips: number }) {
  const positiveMoves = Math.max(moves, 0);
  const positiveChips = Math.max(chips, 0);
  const sum = positiveMoves + positiveChips;
  if (!sum) return <div className="mt-2 h-3 rounded-full bg-slate-100" />;
  return (
    <div className="mt-2 flex h-3 gap-0.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
      {positiveMoves ? <div className="h-full rounded-full" style={{ width: `${(positiveMoves / sum) * 100}%`, background: MOVE_COLOR }} /> : null}
      {positiveChips ? <div className="h-full rounded-full" style={{ width: `${(positiveChips / sum) * 100}%`, background: CHIP_COLOR }} /> : null}
    </div>
  );
}

function LegendValue({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />{label}</div>
      <div className="mt-1 text-lg font-black text-slate-950">{signed(value)} pts</div>
    </div>
  );
}

function RecordPill({ label, value, tone }: { label: string; value: number; tone: "good" | "neutral" | "bad" }) {
  const colors = tone === "good" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : tone === "bad" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <div className={`rounded-2xl border px-3 py-2.5 text-center ${colors}`}>
      <div className="text-2xl font-black">{value}</div>
      <div className="text-[11px] font-bold uppercase tracking-wide">{label}</div>
    </div>
  );
}

function GainChart({ rows }: { rows: TrackRecordGameweek[] }) {
  const data = [...rows]
    .sort((a, b) => a.gameweek - b.gameweek)
    .map((row) => {
      const chip = row.chip_gain ?? 0;
      return { label: `GW${row.gameweek}`, moves: round(row.gain_vs_no_action - chip), chip, total: row.gain_vs_no_action };
    });
  return (
    <div className="mt-4 h-[220px] w-full" role="img" aria-label={`Gain by gameweek: ${data.map((d) => `${d.label} ${signed(d.total)}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} stackOffset="sign" margin={{ top: 8, right: 4, left: -18, bottom: 0 }} barCategoryGap="32%">
          <CartesianGrid vertical={false} stroke="#e2e8f0" strokeDasharray="0" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} height={40} interval={0} tick={<GainTick totals={data.map((d) => d.total)} />} />
          <YAxis tickLine={false} axisLine={false} allowDecimals={false} tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <ReferenceLine y={0} stroke="#94a3b8" />
          <Tooltip cursor={{ fill: "rgba(139,92,246,0.06)" }} content={<GainTooltip />} />
          <Bar dataKey="moves" stackId="gain" fill={MOVE_COLOR} stroke="#ffffff" strokeWidth={2} radius={[4, 4, 4, 4]} maxBarSize={44} isAnimationActive={false} />
          <Bar dataKey="chip" stackId="gain" fill={CHIP_COLOR} stroke="#ffffff" strokeWidth={2} radius={[4, 4, 4, 4]} maxBarSize={44} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Each gameweek's total sits under its label, so a zero-gain week still reads.
function GainTick({ x = 0, y = 0, index = 0, payload, totals }: { x?: number; y?: number; index?: number; payload?: { value: string }; totals: number[] }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <text dy={12} textAnchor="middle" fontSize={12} fontWeight={600} fill="#475569">{payload?.value}</text>
      <text dy={28} textAnchor="middle" fontSize={12} fontWeight={800} fill="#0f172a">{signed(totals[index] ?? 0)}</text>
    </g>
  );
}

function GainTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: { moves: number; chip: number; total: number } }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="font-black text-slate-950">{label} · {signed(point.total)} pts</div>
      <div className="mt-1 flex items-center gap-1.5 text-slate-600"><span className="h-2 w-2 rounded-sm" style={{ background: MOVE_COLOR }} />Transfers & lineup {signed(point.moves)}</div>
      <div className="flex items-center gap-1.5 text-slate-600"><span className="h-2 w-2 rounded-sm" style={{ background: CHIP_COLOR }} />Chip {signed(point.chip)}</div>
    </div>
  );
}

function ScoredRow({ row }: { row: TrackRecordGameweek }) {
  const { recommendation } = row;
  const earlier = !row.current_version;
  return (
    <li className={`grid gap-4 rounded-2xl border border-slate-200 p-4 sm:grid-cols-[88px_minmax(0,1fr)_auto] sm:items-center ${earlier ? "bg-slate-50" : ""}`}>
      <div>
        <div className="text-lg font-black text-slate-950">GW{row.gameweek}</div>
        <div className="text-xs text-slate-500">{formatDay(row.deadline)}</div>
      </div>
      <div className="min-w-0 space-y-2">
        {earlier ? <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">Earlier version{row.chips_considered ? ", chips allowed" : ""} · not in the total</div> : null}
        <div className="flex flex-wrap items-center gap-2">
          {recommendation.transfers.length ? recommendation.transfers.map((move) => (
            <span key={`${move.out}-${move.in}`} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 py-1 pl-1.5 pr-2.5 text-xs font-bold text-slate-800">
              <Repeat2 className="h-3.5 w-3.5 text-slate-400" />
              <span className="text-slate-500 line-through decoration-slate-300">{move.out}</span>
              <span className="text-slate-300">→</span>
              <span>{move.in}</span>
            </span>
          )) : <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-600">No transfer</span>}
          {recommendation.chip ? <span className="inline-flex items-center gap-1 rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-bold text-violet-700"><Sparkles className="h-3.5 w-3.5" />{recommendation.chip}</span> : null}
          {recommendation.hit_cost ? <span className="rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-bold text-rose-700">−{recommendation.hit_cost} hit</span> : null}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          {recommendation.captain ? <span className="inline-flex items-center gap-1 font-semibold text-slate-700"><Crown className="h-3.5 w-3.5 text-amber-500" />{recommendation.captain}</span> : null}
          <span>{row.options_considered} options considered</span>
          <span>Best option {fmt(row.best_option_points)} pts</span>
        </div>
      </div>
      <div className="flex items-center justify-between gap-4 border-t border-slate-100 pt-3 sm:justify-end sm:border-t-0 sm:pt-0">
        <div className="text-xs leading-5 text-slate-500">
          <div>Plan <span className="font-bold text-slate-900">{fmt(row.recommended_points)}</span></div>
          <div>No change <span className="font-bold text-slate-900">{fmt(row.no_action_points)}</span></div>
        </div>
        <div className={`min-w-[84px] rounded-2xl px-3 py-2 text-center ${earlier ? "bg-slate-200/70 text-slate-700" : gainSurface(row.gain_vs_no_action)}`}>
          <div className="text-xl font-black">{signed(row.gain_vs_no_action)}</div>
          <div className="text-[10px] font-bold uppercase tracking-wide opacity-80">{row.chip_gain ? `${signed(row.chip_gain)} chip` : "points"}</div>
        </div>
      </div>
    </li>
  );
}

function UnscoredRow({ from, to }: { from: number; to: number }) {
  const single = from === to;
  return (
    <li className="grid gap-2 rounded-2xl border border-dashed border-slate-200 px-4 py-3 sm:grid-cols-[88px_minmax(0,1fr)] sm:items-center">
      <div className="text-lg font-black text-slate-500">{single ? `GW${from}` : `GW${from}–${to}`}</div>
      <div className="flex items-center gap-2 text-xs text-slate-500"><CalendarX className="h-4 w-4 shrink-0 text-slate-400" />Not scored: no plan was saved before {single ? "this deadline" : "these deadlines"}. Plans are now saved automatically.</div>
    </li>
  );
}

function Step({ n, title, text }: { n: number; title: string; text: string }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-100 text-xs font-black text-violet-700">{n}</span>
      <div><div className="text-sm font-bold text-slate-950">{title}</div><div className="mt-0.5 text-sm leading-6 text-slate-600">{text}</div></div>
    </li>
  );
}

function formatDay(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(date);
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

function gainText(value: number): string {
  if (value > 0) return "text-emerald-700";
  if (value < 0) return "text-rose-700";
  return "text-slate-800";
}

function gainSurface(value: number): string {
  if (value > 0) return "bg-emerald-50 text-emerald-800";
  if (value < 0) return "bg-rose-50 text-rose-800";
  return "bg-slate-100 text-slate-700";
}
