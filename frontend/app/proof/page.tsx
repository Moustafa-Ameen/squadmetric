"use client";

import { CheckCircle2, FlaskConical, ShieldAlert, Target, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/LoadingState";
import { SectionHeader } from "@/components/SectionHeader";
import { getAccuracy, getCaptaincyBacktest, getTop10Metrics } from "@/lib/api";
import { points } from "@/lib/format";
import type { AccuracyResult, BacktestResult, Top10Metric } from "@/lib/types";

export default function ProofPage() {
  const [accuracy, setAccuracy] = useState<AccuracyResult[]>([]);
  const [captaincy, setCaptaincy] = useState<BacktestResult[]>([]);
  const [top10, setTop10] = useState<Top10Metric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([getAccuracy(), getCaptaincyBacktest(), getTop10Metrics()])
      .then(([accuracyRows, captaincyRows, top10Rows]) => {
        setAccuracy(accuracyRows);
        setCaptaincy(captaincyRows.map(renameStrategy));
        setTop10(top10Rows);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const sortedCaptaincy = useMemo(() => [...captaincy].sort((a, b) => b.total_captain_points - a.total_captain_points), [captaincy]);
  if (loading) return <TableSkeleton />;
  if (error) return <ErrorState />;
  if (!accuracy.length) return <EmptyState />;

  const bestAdjusted = [...accuracy].sort((a, b) => a.adjusted_MAE - b.adjusted_MAE)[0];
  const modelCaptain = sortedCaptaincy.find((row) => row.strategy === "SquadMetric");
  const captainRank = modelCaptain ? sortedCaptaincy.findIndex((row) => row.strategy === "SquadMetric") + 1 : null;
  const improvedWithMinutes = accuracy.filter((row) => row.adjusted_MAE < row.raw_MAE).length;

  return (
    <div className="space-y-7">
      <SectionHeader title="Performance evidence" subtitle="A readable view of what has been tested, where the model helps, and what the results do not guarantee." />

      <section className="overflow-hidden rounded-3xl border border-violet-200 bg-[linear-gradient(135deg,#ffffff_0%,#f3f0ff_65%,#ecfdf5_100%)] p-6 shadow-[0_18px_55px_rgba(76,29,149,0.09)] sm:p-8">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 text-white"><FlaskConical className="h-6 w-6" /></div>
        <h2 className="mt-5 max-w-3xl text-2xl font-black tracking-[-0.035em] text-slate-950 sm:text-3xl">The model is tested on matches it was not trained to predict.</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">These results are historical holdout tests. They help us reject weak ideas and compare decision methods honestly. They are evidence of an edge—not a promise of rank or points.</p>
      </section>

      <div className="grid gap-3 md:grid-cols-3">
        <EvidenceCard icon={Target} label="Best start-adjusted MAE" value={`${points(bestAdjusted.adjusted_MAE)} pts`} detail={friendlyModel(bestAdjusted.model)} />
        <EvidenceCard icon={TrendingUp} label="Captain strategy rank" value={captainRank ? `#${captainRank} of ${sortedCaptaincy.length}` : "Not available"} detail={modelCaptain ? `${points(modelCaptain.total_captain_points, 0)} historical captain points` : "No model row returned"} />
        <EvidenceCard icon={CheckCircle2} label="Models helped by minutes adjustment" value={`${improvedWithMinutes} of ${accuracy.length}`} detail="Lower prediction error after availability adjustment" />
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6">
        <div className="mb-5"><h2 className="text-xl font-black text-slate-950">Prediction accuracy</h2><p className="mt-1 text-sm text-slate-600">Average error in FPL points. Lower is better.</p></div>
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Prediction accuracy table">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead><tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500"><th className="pb-3">Model</th><th className="pb-3 text-right">Raw MAE</th><th className="pb-3 text-right">Start-adjusted MAE</th><th className="pb-3 text-right">Change</th><th className="pb-3 text-right">Adjusted RMSE</th></tr></thead>
            <tbody>{[...accuracy].sort((a, b) => a.adjusted_MAE - b.adjusted_MAE).map((row, index) => { const change = row.raw_MAE - row.adjusted_MAE; return <tr key={row.model} className={index === 0 ? "border-b border-emerald-200 bg-emerald-50" : "border-b border-slate-100"}><td className="py-3.5 font-bold text-slate-950">{friendlyModel(row.model)}{index === 0 ? <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-extrabold uppercase text-emerald-700">Best</span> : null}</td><td className="py-3.5 text-right font-semibold text-slate-700">{points(row.raw_MAE)}</td><td className="py-3.5 text-right font-extrabold text-slate-950">{points(row.adjusted_MAE)}</td><td className={`py-3.5 text-right font-bold ${change > 0 ? "text-emerald-700" : "text-rose-700"}`}>{change > 0 ? "−" : "+"}{points(Math.abs(change))}</td><td className="py-3.5 text-right font-semibold text-slate-700">{points(row.adjusted_RMSE)}</td></tr>; })}</tbody>
          </table>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6">
        <div className="mb-5"><h2 className="text-xl font-black text-slate-950">Captaincy backtest</h2><p className="mt-1 text-sm text-slate-600">Total captain points produced by each historical weekly selection rule.</p></div>
        <div className="h-[330px] w-full"><ResponsiveContainer width="100%" height="100%"><BarChart data={sortedCaptaincy} layout="vertical" margin={{ top: 4, right: 40, left: 20, bottom: 4 }}><XAxis type="number" hide /><YAxis dataKey="strategy" type="category" width={165} tick={{ fontSize: 11, fill: "#475569" }} axisLine={false} tickLine={false} /><Tooltip cursor={{ fill: "#f8fafc" }} contentStyle={{ background: "white", border: "1px solid #dce3ec", borderRadius: 12, color: "#0f172a" }} formatter={(value) => [`${points(Number(value), 0)} pts`, "Captain points"]} /><Bar dataKey="total_captain_points" radius={[0, 7, 7, 0]}>{sortedCaptaincy.map((row) => <Cell key={row.strategy} fill={row.strategy === "SquadMetric" ? "#6d3eea" : "#cbd5e1"} />)}</Bar></BarChart></ResponsiveContainer></div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6">
        <div className="mb-5"><h2 className="text-xl font-black text-slate-950">Finding the week&apos;s top players</h2><p className="mt-1 text-sm text-slate-600">Precision asks how many recommended top-10 players truly finished there; recall asks how much of the actual top 10 was found.</p></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{top10.map((row) => <div key={row.model} className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="font-extrabold text-slate-950">{friendlyModel(row.model)}</div><div className="mt-4 grid grid-cols-2 gap-3"><MiniMetric label="Precision" value={percent(row.precision_at_10)} /><MiniMetric label="Recall" value={percent(row.recall_at_10)} /></div></div>)}</div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <EvidenceNote good title="What this evidence supports" items={["The evaluation can compare models on unseen historical gameweeks.", "Minutes-aware projections can be measured against raw projections.", "Captain and player-ranking methods can be compared with simple baselines."]} />
        <EvidenceNote title="What it does not prove" items={["A guaranteed top-1% finish or a fixed season score.", "That every recommended transfer will work in a high-variance game.", "That a lower prediction error automatically creates a better FPL strategy."]} />
      </div>
    </div>
  );
}

function EvidenceCard({ icon: Icon, label, value, detail }: { icon: typeof Target; label: string; value: string; detail: string }) { return <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)]"><Icon className="h-5 w-5 text-violet-600" /><div className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-500">{label}</div><div className="mt-1 text-2xl font-black text-slate-950">{value}</div><div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div></div>; }
function MiniMetric({ label, value }: { label: string; value: string }) { return <div><div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</div><div className="mt-1 text-xl font-black text-slate-950">{value}</div></div>; }
function EvidenceNote({ good = false, title, items }: { good?: boolean; title: string; items: string[] }) { return <section className={`rounded-2xl border p-5 ${good ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}><div className={`flex items-center gap-2 font-black ${good ? "text-emerald-950" : "text-amber-950"}`}>{good ? <CheckCircle2 className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}{title}</div><ul className={`mt-3 space-y-2 text-sm leading-6 ${good ? "text-emerald-900" : "text-amber-900"}`}>{items.map((item) => <li key={item} className="flex gap-2"><span aria-hidden="true">•</span><span>{item}</span></li>)}</ul></section>; }
function renameStrategy(row: BacktestResult): BacktestResult { const names: Record<string, string> = { "FPL Intelligence (best)": "SquadMetric", "Ridge (Captaincy Model)": "Ridge model", "No model (form average)": "Form average", "Most popular player": "Most popular", "Best points-per-game": "Highest PPG", "Random pick": "Random pick" }; return { ...row, strategy: names[row.strategy] ?? row.strategy }; }
function friendlyModel(model: string): string { return model === "FPL Intelligence (best)" ? "SquadMetric" : model; }
function percent(value: number) { return `${Math.round((value <= 1 ? value * 100 : value) * 10) / 10}%`; }
