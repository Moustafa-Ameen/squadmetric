import type { SupabaseClient } from "@supabase/supabase-js";
import type { TeamData } from "@/lib/types";

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
  supabase,
  teamId,
  sourceInput,
  team,
  preferences,
}: {
  supabase: SupabaseClient | null;
  teamId: string;
  sourceInput: string;
  team: TeamData;
  preferences: OnboardingPreferences;
}) {
  window.localStorage.setItem("fpl_team_id", teamId);
  window.localStorage.setItem("squadmetric_preferences", JSON.stringify(preferences));

  if (!supabase) return { storage: "local" as const };
  const { data, error: userError } = await supabase.auth.getUser();
  if (userError || !data.user) throw userError ?? new Error("Your session has expired. Sign in again.");

  const userId = data.user.id;
  const [profileResult, linkResult, preferenceResult] = await Promise.all([
    supabase.from("profiles").upsert({ user_id: userId, onboarding_completed: true }),
    supabase.from("fpl_team_links").upsert({
      user_id: userId,
      team_id: Number(teamId),
      source_input: sourceInput,
      verified_team_name: team.team_name,
      verified_at: new Date().toISOString(),
    }),
    supabase.from("user_preferences").upsert({
      user_id: userId,
      risk_style: preferences.riskStyle,
      alternative_style: preferences.alternativeStyle,
      deadline_reminders: preferences.deadlineReminders,
      email_notifications: preferences.emailNotifications,
    }),
  ]);

  const failure = profileResult.error ?? linkResult.error ?? preferenceResult.error;
  if (failure) throw failure;
  return { storage: "account" as const };
}
