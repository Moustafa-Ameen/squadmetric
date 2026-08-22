import { AlertTriangle, CheckCircle2, DatabaseZap, ShieldAlert } from "lucide-react";
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
  const Icon = ready ? CheckCircle2 : unavailable ? DatabaseZap : ShieldAlert;
  const age = seasonState.artifact_data.age_hours;

  return (
    <section
      data-testid="decision-status"
      data-decision-status={seasonState.decision_status}
      className={`rounded-lg border p-4 ${
        ready
          ? "border-fpl-green/30 bg-fpl-green/10"
          : "border-fpl-red/40 bg-fpl-red/10"
      }`}
      role={ready ? "status" : "alert"}
    >
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${ready ? "text-fpl-green" : "text-fpl-red"}`} />
        <div className="min-w-0">
          <div className="font-semibold text-primary">{decisionStatusLabel(seasonState)}</div>
          {ready ? (
            <p className="mt-1 text-sm text-secondary">
              Official FPL inputs match the processed player pool and the recommendation cutoff is current.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm text-secondary">
                Decision recommendations are hidden until the data refresh and validation complete.
                {typeof age === "number" ? ` Current artifacts are ${age.toFixed(1)} hours old.` : ""}
              </p>
              {!compact && seasonState.decision_blockers.length ? (
                <ul className="mt-3 space-y-1 text-sm text-secondary">
                  {seasonState.decision_blockers.map((blocker) => (
                    <li key={`${blocker.code}-${blocker.message}`} className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-fpl-amber" />
                      <span>{blocker.message}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
          <div className="mt-2 text-[11px] uppercase tracking-[0.08em] text-muted">
            Checked {formatTimestamp(seasonState.live_data.checked_at)} · rules {seasonState.artifact_data.rules_version ?? "unavailable"}
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
