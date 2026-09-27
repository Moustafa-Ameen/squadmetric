import type { ScreenshotAnalysis } from "@/lib/types";
import { ACCOUNT_STORAGE_KEYS } from "@/lib/accountStorage";

export type RiskStyle = "safe" | "balanced" | "aggressive";
export type AlternativeStyle = "popular" | "differential" | "both";

export type OnboardingPreferences = {
  riskStyle: RiskStyle;
  alternativeStyle: AlternativeStyle;
  deadlineReminders: boolean;
  emailNotifications: boolean;
};

export const DEFAULT_ONBOARDING_PREFERENCES: OnboardingPreferences = {
  riskStyle: "balanced",
  alternativeStyle: "both",
  deadlineReminders: true,
  emailNotifications: false,
};

export async function persistOnboarding({
  teamId,
  preferences,
}: {
  teamId: string;
  preferences: OnboardingPreferences;
}) {
  window.localStorage.setItem("fpl_team_id", teamId);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.provisionalSquad);
  window.localStorage.setItem("squadmetric_preferences", JSON.stringify(preferences));

  return { storage: "browser" as const };
}

export async function persistProvisionalOnboarding({
  analysis,
  preferences,
}: {
  analysis: ScreenshotAnalysis;
  preferences: OnboardingPreferences;
}) {
  window.localStorage.removeItem("fpl_team_id");
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.provisionalSquad, JSON.stringify(analysis));
  window.localStorage.setItem("squadmetric_preferences", JSON.stringify(preferences));
  return { storage: "browser" as const };
}
