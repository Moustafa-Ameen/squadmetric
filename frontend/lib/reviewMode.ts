export type ReviewMode = "points" | "rank";

export function parseReviewMode(value: string | null): ReviewMode {
  return value === "rank" ? "rank" : "points";
}

export function rankMovementLabel(change: number | null): string {
  if (change === null) return "Opening rank";
  if (change > 0) return `Up ${change.toLocaleString()}`;
  if (change < 0) return `Down ${Math.abs(change).toLocaleString()}`;
  return "No change";
}
