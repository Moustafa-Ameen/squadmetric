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
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.teamId);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.guestDemo, "true");
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.provisionalSquad);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.onboardingPreferences, JSON.stringify(preferences));
  return { storage: "browser" as const };
}
