"use client";

import { Check, CircleAlert, Clock3, DatabaseZap, LockKeyhole, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getDeadlineReadiness } from "@/lib/api";
import {
  checklistProgress,
  DEADLINE_CHECK_LABELS,
  deadlineAction,
  deadlineUrgency,
} from "@/lib/deadlineIntelligence";
import type { DeadlineReadinessResponse } from "@/lib/types";

export default function DeadlinePage() {
  const [data, setData] = useState<DeadlineReadinessResponse | null>(null);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    getDeadlineReadiness()
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const hoursToDeadline = data?.deadline
    ? (new Date(data.deadline).getTime() - now) / 3_600_000
    : null;

  if (error) return <ErrorState />;
  if (!data) return <PlannerSkeleton />;

  const progress = checklistProgress(data.checklist);
  const finalNewsReviewed = data.p11?.final_news_reviewed ?? false;
  const action = deadlineAction(hoursToDeadline, data.decision_lock_ready, finalNewsReviewed);
  const urgency = deadlineUrgency(hoursToDeadline);

  return (
    <div className="space-y-5">
      <SectionHeader
        title={`GW${data.next_gameweek ?? "—"} Deadline Intelligence`}
        subtitle="One fail-closed checklist for freshness, official news, roles, and the frozen decision"
      />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <div className={`text-xs font-bold uppercase tracking-[0.12em] ${data.decision_lock_ready ? "text-fpl-green" : urgency === "urgent" ? "text-fpl-red" : "text-fpl-yellow"}`}>
              {data.decision_lock_ready ? "Ready to lock" : urgency === "monitor" ? "Monitoring window" : "Action required"}
            </div>
            <h2 className="mt-2 text-2xl font-bold text-primary">{action.title}</h2>
            <p className="mt-2 text-sm text-secondary">{action.detail}</p>
          </div>
          <div className="rounded-xl border border-fpl-border bg-fpl-raised px-5 py-4 text-right">
            <div className="text-[10px] uppercase tracking-[0.1em] text-muted">Official deadline</div>
            <div className="mt-1 text-lg font-bold text-primary">{formatDeadline(data.deadline)}</div>
            <div className="mt-1 font-mono text-sm text-fpl-green">{formatCountdown(hoursToDeadline)}</div>
          </div>
        </div>
        <div className="mt-5 h-2 overflow-hidden rounded-full bg-fpl-raised" role="progressbar" aria-label="Deadline checklist completion" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.percent}>
          <div className="h-full rounded-full bg-fpl-green transition-[width]" style={{ width: `${progress.percent}%` }} />
        </div>
        <p className="mt-2 text-xs text-muted">{progress.passed} of {progress.total} deadline checks passed</p>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="Lock checklist">
          <div className="space-y-2">
            {data.checklist.map((item) => (
              <div key={item.key} className="flex items-center gap-3 rounded-lg border border-fpl-border bg-fpl-raised px-3 py-3">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${item.passed ? "bg-fpl-green/15 text-fpl-green" : "bg-fpl-red/10 text-fpl-red"}`}>
                  {item.passed ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                </span>
                <span className="text-sm font-medium text-primary">{DEADLINE_CHECK_LABELS[item.key] ?? item.key.replaceAll("_", " ")}</span>
              </div>
            ))}
          </div>
          {data.blockers.length ? (
            <div className="mt-4 rounded-lg border border-fpl-red/30 bg-fpl-red/10 p-4" role="alert">
              <div className="flex items-center gap-2 text-sm font-semibold text-fpl-red"><CircleAlert className="h-4 w-4" /> Blocking issues</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-secondary">{data.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
            </div>
          ) : null}
        </Panel>

        <div className="space-y-5">
          <Panel title="Frozen evidence">
            {data.latest_shadow ? (
              <div className="space-y-3 text-sm">
                <Evidence icon={<LockKeyhole className="h-4 w-4" />} label="Snapshot" value={data.latest_shadow.current ? "Current" : "Outdated"} good={data.latest_shadow.current} />
                <Evidence icon={<Clock3 className="h-4 w-4" />} label="Captured" value={formatDeadline(data.latest_shadow.captured_at)} />
                <Evidence icon={<DatabaseZap className="h-4 w-4" />} label="Decision hash" value={data.latest_shadow.decision_hash.slice(0, 12)} />
                <Evidence icon={<Check className="h-4 w-4" />} label="Expected GW1" value={`${data.latest_shadow.expected_gw1_points.toFixed(1)} pts`} />
              </div>
            ) : <p className="text-sm text-muted">No immutable decision has been captured for this deadline.</p>}
          </Panel>
          <Panel title="Next actions">
            <div className="space-y-2">
              <Link href="/decisions" className="fpl-button block px-4 py-2 text-center text-sm">Review complete decision</Link>
              <Link href="/drafts" className="block rounded-lg border border-fpl-border bg-fpl-raised px-4 py-2 text-center text-sm font-semibold text-primary">Compare squad drafts</Link>
            </div>
            <p className="mt-4 text-[11px] text-muted">This page never executes transfers or chips. The final-news acknowledgement remains a reviewed operational step.</p>
          </Panel>
        </div>
      </div>

      <p className="text-[11px] text-muted">Data cutoff {data.data_cutoff} · age {data.data_age_hours.toFixed(2)}h · season {data.season}</p>
    </div>
  );
}

function Evidence({ icon, label, value, good }: { icon: React.ReactNode; label: string; value: string; good?: boolean }) {
  return <div className="flex items-center justify-between gap-3 rounded-lg border border-fpl-border bg-fpl-raised p-3"><span className="flex items-center gap-2 text-secondary">{icon}{label}</span><span className={`font-mono text-xs ${good ? "text-fpl-green" : "text-primary"}`}>{value}</span></div>;
}

function formatDeadline(value: string | null): string {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(date);
}

function formatCountdown(hours: number | null): string {
  if (hours === null || !Number.isFinite(hours)) return "Countdown unavailable";
  if (hours < 0) return "Deadline passed";
  const totalMinutes = Math.max(0, Math.floor(hours * 60));
  const days = Math.floor(totalMinutes / 1_440);
  const remainingHours = Math.floor((totalMinutes % 1_440) / 60);
  const minutes = totalMinutes % 60;
  return `${days ? `${days}d ` : ""}${remainingHours}h ${minutes}m remaining`;
}
