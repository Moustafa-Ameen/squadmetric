"use client";

import { BarChart3, ShieldCheck, Target } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getPostGameweekReview } from "@/lib/api";
import type { PostGameweekReviewResponse } from "@/lib/types";

export default function ReviewPage() {
  const [teamId, setTeamId] = useState("");
  const [data, setData] = useState<PostGameweekReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    queueMicrotask(() => setTeamId(savedTeamId));
    if (!savedTeamId) {
      queueMicrotask(() => setLoading(false));
      return () => { cancelled = true; };
    }
    getPostGameweekReview(savedTeamId)
      .then((response) => { if (!cancelled) setData(response); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <PlannerSkeleton />;
  if (error) return <ErrorState />;
  if (!teamId) {
    return <div className="space-y-5"><SectionHeader title="Your Results" subtitle="See how your weekly decisions performed after scores are final" /><Panel><p className="text-sm text-slate-600">Connect your FPL team before reviewing personalized results.</p><Link href="/onboarding" className="sm-primary-button mt-4 px-4 py-2 text-sm">Connect team</Link></Panel></div>;
  }
  if (!data) return <ErrorState />;

  return (
    <div className="space-y-6">
      <SectionHeader title="Your Results" subtitle={"Team #" + teamId + " · only finalized gameweeks appear here"} />
      {data.gameweeks.length === 0 ? (
        <Panel>
          <div className="py-8 text-center"><ShieldCheck className="mx-auto h-8 w-8 text-emerald-600" /><h2 className="mt-3 text-lg font-bold text-slate-950">Waiting for the first finalized gameweek</h2><p className="mx-auto mt-2 max-w-xl text-sm text-slate-500">Your results will appear after official scoring is complete and checked.</p></div>
        </Panel>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Summary label="Total points" value={data.summary.net_points.toFixed(0)} />
            <Summary label="Transfer costs" value={"-" + data.summary.hit_cost.toFixed(0)} warning={data.summary.hit_cost > 0} />
            <Summary label="Bench points" value={data.summary.points_on_bench.toFixed(0)} />
            <Summary label="Weeks reviewed" value={String(data.reviewed_gameweeks)} />
            <Summary label="Better alternative" value={data.summary.decision_regret.toFixed(1) + " pts"} warning={data.summary.decision_regret > 0} />
          </div>
          <Panel title="Gameweek results">
            <div className="overflow-x-auto">
              <table className="min-w-[760px] w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-[10px] uppercase tracking-[0.08em] text-slate-500"><tr><th className="px-3 py-2">GW</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Transfer cost</th><th className="px-3 py-2">Bench</th><th className="px-3 py-2">Expected</th><th className="px-3 py-2">Better alternative</th><th className="px-3 py-2">Record</th></tr></thead>
                <tbody>{data.gameweeks.map((row) => {
                  const evidence = row.decision_evidence;
                  return <tr key={row.gameweek} className="border-b border-slate-100 last:border-0"><td className="px-3 py-3 font-bold text-slate-950">GW{row.gameweek}</td><td className="px-3 py-3 font-bold text-emerald-700">{row.net_points.toFixed(0)}</td><td className="px-3 py-3 text-slate-600">{row.hit_cost ? "-" + row.hit_cost : "0"}</td><td className="px-3 py-3 text-slate-600">{row.points_on_bench.toFixed(0)}</td><td className="px-3 py-3 text-slate-700">{evidence.expected_points?.toFixed(1) ?? "—"}</td><td className="px-3 py-3 text-slate-600">{evidence.selected_regret?.toFixed(1) ?? "—"}</td><td className="px-3 py-3"><span className={evidence.status === "finalized" ? "text-emerald-700" : "text-amber-700"}>{evidence.status === "finalized" ? "Recommendation recorded" : "No recommendation saved"}</span></td></tr>;
                })}</tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
      <Panel title="How to read your results">
        <div className="grid gap-3 md:grid-cols-3"><ReviewPrinciple icon={<Target className="h-5 w-5" />} title="Review decisions, not luck" text="A good decision can still have a bad one-week result." /><ReviewPrinciple icon={<BarChart3 className="h-5 w-5" />} title="Compare like with like" text="Alternatives use only information available before that deadline." /><ReviewPrinciple icon={<ShieldCheck className="h-5 w-5" />} title="Wait for final scores" text="Provisional bonus points never enter this review." /></div>
      </Panel>
    </div>
  );
}

function Summary({ label, value, warning }: { label: string; value: string; warning?: boolean }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">{label}</div><div className={"mt-2 text-2xl font-black " + (warning ? "text-amber-700" : "text-slate-950")}>{value}</div></div>;
}
function ReviewPrinciple({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><span className="text-violet-700">{icon}</span><h3 className="mt-2 text-sm font-bold text-slate-950">{title}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{text}</p></div>;
}
