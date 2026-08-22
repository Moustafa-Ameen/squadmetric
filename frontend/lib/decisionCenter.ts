import type { DecisionCenterRecommendation } from "./types";

export function decisionHeadline(recommendation: DecisionCenterRecommendation): string {
  const transfer = recommendation.transfer_count === 0
    ? "Roll the transfer"
    : `Make ${recommendation.transfer_count} transfer${recommendation.transfer_count === 1 ? "" : "s"}`;
  const hit = recommendation.hit_recommended ? ` for a -${recommendation.hit_cost}` : "";
  const chip = recommendation.chip_action === "save"
    ? "Save chips"
    : `Use ${formatChip(recommendation.chip_action)}`;
  return `${transfer}${hit} · ${chip}`;
}

export function recommendationIsComplete(recommendation?: DecisionCenterRecommendation): boolean {
  if (!recommendation) return false;
  return (
    recommendation.starting_xi.length === 11 &&
    recommendation.bench_order.length === 4 &&
    recommendation.captain_id !== null &&
    recommendation.vice_captain_id !== null &&
    recommendation.starting_xi.some((player) => player.element_id === recommendation.captain_id) &&
    recommendation.starting_xi.some((player) => player.element_id === recommendation.vice_captain_id)
  );
}

export function formatChip(value: string): string {
  const labels: Record<string, string> = {
    wildcard: "Wildcard",
    freehit: "Free Hit",
    bboost: "Bench Boost",
    "3xc": "Triple Captain",
  };
  return labels[value] ?? value;
}
