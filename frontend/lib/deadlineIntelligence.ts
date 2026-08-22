import type { DeadlineChecklistItem } from "./types";

export type DeadlineUrgency = "monitor" | "final_window" | "urgent" | "passed" | "unknown";

export function deadlineUrgency(hoursToDeadline: number | null): DeadlineUrgency {
  if (hoursToDeadline === null || !Number.isFinite(hoursToDeadline)) return "unknown";
  if (hoursToDeadline < 0) return "passed";
  if (hoursToDeadline <= 2) return "urgent";
  if (hoursToDeadline <= 24) return "final_window";
  return "monitor";
}

export function deadlineAction(
  hoursToDeadline: number | null,
  decisionLockReady: boolean,
  finalNewsReviewed: boolean,
): { title: string; detail: string } {
  if (decisionLockReady) {
    return {
      title: "Decision lock is ready",
      detail: "The current data, final-news review, and immutable snapshot checks have all passed.",
    };
  }
  const urgency = deadlineUrgency(hoursToDeadline);
  if (urgency === "urgent" || urgency === "final_window") {
    return finalNewsReviewed
      ? {
          title: "Refresh and freeze the final decision",
          detail: "Final news is reviewed; rebuild once more and verify the immutable snapshot before the deadline.",
        }
      : {
          title: "Final team-news review required",
          detail: "Do not treat the current recommendation as locked until official team news has been reviewed and recorded.",
        };
  }
  if (urgency === "passed") {
    return {
      title: "Deadline has passed",
      detail: "Wait for official finalization; recommendations must not be rewritten with post-deadline information.",
    };
  }
  return {
    title: "Monitor; do not lock yet",
    detail: "The current recommendation is usable for planning, but the final 24-hour refresh window has not opened.",
  };
}

export function checklistProgress(checklist: DeadlineChecklistItem[]): {
  passed: number;
  total: number;
  percent: number;
} {
  const passed = checklist.filter((item) => item.passed).length;
  return {
    passed,
    total: checklist.length,
    percent: checklist.length ? Math.round((passed / checklist.length) * 100) : 0,
  };
}

export const DEADLINE_CHECK_LABELS: Record<string, string> = {
  fresh_data: "Official data refreshed",
  official_deadline: "Official deadline found",
  robustness_current: "Robustness scenarios current",
  set_piece_roles_current: "Set-piece roles current",
  shadow_captured: "Immutable decision captured",
  final_team_news: "Final official team news reviewed",
};
