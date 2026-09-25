import { AlertTriangle, CheckCircle2, DatabaseZap } from "lucide-react";
import { decisionStatusLabel, recommendationsAreReady, squadAccessMessage } from "@/lib/decisionState";
import type { SquadAccessState } from "@/lib/decisionState";
import type { SeasonState } from "@/lib/types";

export function DecisionStatusNotice({
  seasonState,
  compact = false,
}: {
  seasonState: SeasonState;
  compact?: boolean;
}) {
  const ready = recommendationsAreReady(seasonState);
  const unavailable = seasonState.decision_status === "unavailable";
  const Icon = ready ? CheckCircle2 : unavailable ? DatabaseZap : AlertTriangle;
  const primaryBlocker = seasonState.decision_blockers[0]?.message;
  const statusSummary = unavailable
    ? primaryBlocker ?? "Official FPL data cannot be reached right now."
    : `${primaryBlocker ?? "The latest prediction data is not ready."} Team, fixtures and official player data remain available.`;
  const tone = ready
    ? "border-emerald-200 bg-emerald-50"
    : unavailable
      ? "border-rose-200 bg-rose-50"
      : "border-amber-200 bg-amber-50";
  const iconTone = ready
    ? "text-emerald-700"
    : unavailable
      ? "text-rose-700"
      : "text-amber-700";

  return (
    <section
      data-testid="decision-status"
      data-decision-status={seasonState.decision_status}
      className={`rounded-2xl border p-4 ${tone}`}
      role={unavailable ? "alert" : "status"}
    >
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${iconTone}`} />
        <div className="min-w-0">
          <div className="font-semibold text-primary">{decisionStatusLabel(seasonState)}</div>
          {ready ? (
            <p className="mt-1 text-sm text-secondary">
              Official FPL inputs match the processed player pool and the recommendation cutoff is current.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm text-secondary">
                {statusSummary}
              </p>
              {!compact && seasonState.decision_blockers.length > 1 ? (
                <ul className="mt-3 space-y-1 text-sm text-secondary">
                  {seasonState.decision_blockers.slice(1).map((blocker) => (
                    <li key={`${blocker.code}-${blocker.message}`} className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-fpl-amber" />
                      <span>{blocker.message}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
          <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            Last checked {formatTimestamp(seasonState.live_data.checked_at)}
          </div>
        </div>
      </div>
    </section>
  );
}

export function SquadScopeNotice({ state }: { state: SquadAccessState }) {
  if (state === "personalized" || state === "no_team") return null;
  return (
    <div
      data-testid="squad-scope"
      data-squad-state={state}
      className="rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 px-4 py-3 text-sm text-secondary"
      role="status"
    >
      {squadAccessMessage(state)}
    </div>
  );
}

function formatTimestamp(value?: string | null): string {
  if (!value) return "unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(parsed);
}
