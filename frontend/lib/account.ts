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

// A public team used only to let visitors explore the complete product before linking their own team.
export const GUEST_DEMO_TEAM_ID = "3254925";

export async function persistOnboarding({
  teamId,
  preferences,
}: {
  teamId: string;
  preferences: OnboardingPreferences;
}) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.teamId, teamId);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.provisionalSquad);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.guestDemo);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.onboardingPreferences, JSON.stringify(preferences));

  return { storage: "browser" as const };
}

export async function persistGuestDemo({
  preferences,
}: {
  preferences: OnboardingPreferences;
}) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.teamId, GUEST_DEMO_TEAM_ID);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.guestDemo, "true");
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.provisionalSquad);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.onboardingPreferences, JSON.stringify(preferences));
  return { storage: "browser" as const };
}
