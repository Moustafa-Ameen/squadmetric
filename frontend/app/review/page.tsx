"use client";

import { ArrowDownRight, ArrowUpRight, BarChart3, ShieldCheck, Target } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getPostGameweekReview } from "@/lib/api";
import { parseReviewMode, rankMovementLabel } from "@/lib/reviewMode";
import type { PostGameweekReviewResponse } from "@/lib/types";
import type { ReviewMode } from "@/lib/reviewMode";

const MODE_STORAGE_KEY = "fpl_decision_objective_mode";

export default function ReviewPage() {
  const [teamId, setTeamId] = useState("");
  const [mode, setMode] = useState<ReviewMode>("points");
  const [data, setData] = useState<PostGameweekReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
      setTeamId(savedTeamId);
      setMode(parseReviewMode(window.localStorage.getItem(MODE_STORAGE_KEY)));
      if (!savedTeamId) {
        setLoading(false);
        return;
      }
      getPostGameweekReview(savedTeamId)
        .then((response) => {
          if (!cancelled) setData(response);
        })
        .catch(() => {
          if (!cancelled) setError(true);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  function selectMode(next: ReviewMode) {
    window.localStorage.setItem(MODE_STORAGE_KEY, next);
    setMode(next);
  }

  if (loading) return <PlannerSkeleton />;
  if (error) return <ErrorState />;
  if (!teamId) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Post-GW Review" subtitle="Official score, decision evidence, and lessons after finalization" />
        <Panel><p className="text-sm text-secondary">Add your FPL Team ID before reviewing personalized Gameweek results.</p><Link href="/settings" className="fpl-button mt-4 inline-block px-4 py-2 text-sm">Open settings</Link></Panel>
      </div>
    );
  }
  if (!data) return <ErrorState />;

  return (
    <div className="space-y-5">
      <SectionHeader title={`${data.season} Post-GW Review`} subtitle="Only officially finished and data-checked Gameweeks appear here" />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.12em] text-fpl-green">Objective lens</div>
            <h2 className="mt-2 text-xl font-semibold text-primary">{mode === "points" ? "Points mode" : "Rank review mode"}</h2>
            <p className="mt-2 max-w-2xl text-sm text-secondary">
              {mode === "points"
                ? "Production recommendations continue to maximize expected FPL points."
                : data.rank_mode.reason}
            </p>
          </div>
          <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1" aria-label="Review objective">
            <ModeButton active={mode === "points"} onClick={() => selectMode("points")} label="Points" />
            <ModeButton active={mode === "rank"} onClick={() => selectMode("rank")} label="Rank (review only)" />
          </div>
        </div>
        {mode === "rank" ? <div className="mt-4 rounded-lg border border-fpl-yellow/30 bg-fpl-yellow/10 p-3 text-xs text-secondary" role="note"><strong className="text-fpl-yellow">Not a production optimizer objective.</strong> Rank mode visualizes field-relative outcomes only; it cannot silently change transfers, captaincy, or chips.</div> : null}
      </Panel>

      {data.gameweeks.length === 0 ? (
        <Panel>
          <div className="py-8 text-center"><ShieldCheck className="mx-auto h-8 w-8 text-fpl-green" /><h2 className="mt-3 text-lg font-semibold text-primary">Waiting for the first finalized Gameweek</h2><p className="mx-auto mt-2 max-w-xl text-sm text-muted">GW1 recommendations are already frozen. This review will populate only after official scoring is marked finished and data checked.</p></div>
        </Panel>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Summary label="Net points" value={data.summary.net_points.toFixed(0)} />
            <Summary label="Transfer hits" value={`-${data.summary.hit_cost.toFixed(0)}`} warning={data.summary.hit_cost > 0} />
            <Summary label="Bench points" value={data.summary.points_on_bench.toFixed(0)} />
            <Summary label="Frozen decisions" value={`${data.summary.decision_evidence_gameweeks}/${data.reviewed_gameweeks}`} />
            <Summary label="Frozen-branch regret" value={data.summary.decision_regret.toFixed(1)} warning={data.summary.decision_regret > 0} />
          </div>

          <Panel title={mode === "points" ? "Gameweek score audit" : "Gameweek rank audit"}>
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full text-left text-sm">
                <thead className="border-b border-fpl-border text-[10px] uppercase tracking-[0.08em] text-muted"><tr><th className="px-3 py-2">GW</th><th className="px-3 py-2">Net score</th><th className="px-3 py-2">Hits</th><th className="px-3 py-2">Bench</th><th className="px-3 py-2">{mode === "rank" ? "Overall rank" : "Expected"}</th><th className="px-3 py-2">{mode === "rank" ? "Movement" : "Frozen regret"}</th><th className="px-3 py-2">Evidence</th></tr></thead>
                <tbody>{data.gameweeks.map((row) => {
                  const evidence = row.decision_evidence;
                  const rankUp = (row.rank_change ?? 0) > 0;
                  return <tr key={row.gameweek} className="border-b border-fpl-border/60 last:border-0"><td className="px-3 py-3 font-bold text-primary">GW{row.gameweek}</td><td className="px-3 py-3 font-mono font-bold text-fpl-green">{row.net_points.toFixed(0)}</td><td className="px-3 py-3 font-mono text-secondary">{row.hit_cost ? `-${row.hit_cost}` : "0"}</td><td className="px-3 py-3 font-mono text-secondary">{row.points_on_bench.toFixed(0)}</td><td className="px-3 py-3 font-mono text-primary">{mode === "rank" ? row.overall_rank?.toLocaleString() ?? "—" : evidence.expected_points?.toFixed(1) ?? "—"}</td><td className="px-3 py-3">{mode === "rank" ? <span className={`inline-flex items-center gap-1 ${rankUp ? "text-fpl-green" : row.rank_change && row.rank_change < 0 ? "text-fpl-red" : "text-muted"}`}>{rankUp ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}{rankMovementLabel(row.rank_change)}</span> : <span className="font-mono text-secondary">{evidence.selected_regret?.toFixed(1) ?? "—"}</span>}</td><td className="px-3 py-3"><span className={evidence.status === "finalized" ? "text-fpl-green" : "text-fpl-yellow"}>{evidence.status === "finalized" ? "Frozen + settled" : "Not captured"}</span></td></tr>;
                })}</tbody>
              </table>
            </div>
          </Panel>
        </>
      )}

      <Panel title="How to use this review">
        <div className="grid gap-3 md:grid-cols-3"><ReviewPrinciple icon={<Target className="h-5 w-5" />} title="Judge decisions, not luck" text="Compare the selected branch only with choices frozen before the same deadline." /><ReviewPrinciple icon={<BarChart3 className="h-5 w-5" />} title="Separate score from rank" text="Rank movement depends on the field; points remain the production objective." /><ReviewPrinciple icon={<ShieldCheck className="h-5 w-5" />} title="Wait for final scoring" text="Provisional BPS or defensive-contribution reviews never enter this page." /></div>
      </Panel>
    </div>
  );
}

function ModeButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-md px-3 py-2 text-xs font-semibold ${active ? "bg-fpl-green text-fpl-dark" : "text-secondary"}`}>{label}</button>;
}

function Summary({ label, value, warning }: { label: string; value: string; warning?: boolean }) {
  return <div className="rounded-xl border border-fpl-border bg-fpl-card p-4"><div className="text-[10px] uppercase tracking-[0.08em] text-muted">{label}</div><div className={`mt-2 font-mono text-2xl font-bold ${warning ? "text-fpl-yellow" : "text-primary"}`}>{value}</div></div>;
}

function ReviewPrinciple({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="rounded-lg border border-fpl-border bg-fpl-raised p-4"><span className="text-fpl-green">{icon}</span><h3 className="mt-2 text-sm font-semibold text-primary">{title}</h3><p className="mt-1 text-xs text-muted">{text}</p></div>;
}
