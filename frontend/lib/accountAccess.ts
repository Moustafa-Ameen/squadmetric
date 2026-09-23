export type AccountProfileState = {
  onboarding_completed?: boolean | null;
  terms_accepted_at?: string | null;
} | null;

export function deriveAccountAccess(profile: AccountProfileState, teamId: number | string | null | undefined, hasProvisionalSquad = false) {
  const normalizedTeamId = Number(teamId);
  const hasTeam = Number.isInteger(normalizedTeamId) && normalizedTeamId > 0;
  return {
    requiresConsent: !profile?.terms_accepted_at,
    requiresOnboarding: !profile?.onboarding_completed || (!hasTeam && !hasProvisionalSquad),
    teamId: hasTeam ? normalizedTeamId : null,
  };
}

export function applyAuthoritativeTeamId(
  storage: Pick<Storage, "setItem" | "removeItem">,
  teamId: number | string | null | undefined,
) {
  const normalizedTeamId = Number(teamId);
  if (Number.isInteger(normalizedTeamId) && normalizedTeamId > 0) {
    storage.setItem("fpl_team_id", String(normalizedTeamId));
    return normalizedTeamId;
  }
  storage.removeItem("fpl_team_id");
  return null;
}
