import type { SeasonState } from "./types";

export type SquadAccessState =
  | "no_team"
  | "loading"
  | "personalized"
  | "squad_unavailable"
  | "invalid_team"
  | "service_unavailable";

export function recommendationsAreReady(state?: SeasonState | null): boolean {
  return state?.decision_status === "ready" && state.recommendations_ready === true;
}

export function decisionStatusLabel(state?: SeasonState | null): string {
  if (!state) return "Decision status unavailable";
  if (recommendationsAreReady(state)) return "Recommendations current";
  if (state.decision_status === "unavailable") return "Live FPL data unavailable";
  return "Recommendations updating";
}

export function squadAccessState(
  teamId: string | null | undefined,
  squadCount: number,
  errorCode?: string | null,
  loading = false,
): SquadAccessState {
  if (!teamId) return "no_team";
  if (loading) return "loading";
  if (squadCount > 0) return "personalized";
  if (errorCode === "squad_unavailable") return "squad_unavailable";
  if (errorCode === "fpl_resource_not_found") return "invalid_team";
  return "service_unavailable";
}

export function squadAccessMessage(state: SquadAccessState): string {
  switch (state) {
    case "personalized":
      return "Recommendations use your successfully loaded FPL squad.";
    case "loading":
      return "Checking whether your saved Team ID has a public squad.";
    case "squad_unavailable":
      return "Your Team ID is saved, but public squad picks are not available yet. Showing generic advice.";
    case "invalid_team":
      return "The saved Team ID could not be found. Showing generic advice until it is corrected.";
    case "service_unavailable":
      return "Your Team ID is saved, but the squad could not be loaded. Showing generic advice.";
    default:
      return "Save a Team ID to enable squad-aware recommendations when public picks are available.";
  }
}
