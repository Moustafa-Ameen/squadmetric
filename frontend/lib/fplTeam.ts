export type ParsedFplTeam = {
  teamId: string;
  source: "team_id" | "fpl_url";
};

export type FplTeamParseResult =
  | { ok: true; value: ParsedFplTeam }
  | { ok: false; error: string };

const MAX_TEAM_ID = 2_147_483_647;

function validateTeamId(value: string, source: ParsedFplTeam["source"]): FplTeamParseResult {
  if (!/^\d+$/.test(value)) {
    return { ok: false, error: "Enter a numeric FPL Team ID or a valid fantasy.premierleague.com team URL." };
  }

  const normalized = value.replace(/^0+/, "") || "0";
  const numeric = Number(normalized);
  if (!Number.isSafeInteger(numeric) || numeric < 1 || numeric > MAX_TEAM_ID) {
    return { ok: false, error: "Enter a valid positive FPL Team ID." };
  }

  return { ok: true, value: { teamId: normalized, source } };
}

export function parseFplTeamInput(input: string): FplTeamParseResult {
  const value = input.trim();
  if (!value) return { ok: false, error: "Enter your FPL Team ID or team URL." };
  if (/^\d+$/.test(value)) return validateTeamId(value, "team_id");

  let url: URL;
  try {
    const normalizedUrl = /^(?:www\.)?fantasy\.premierleague\.com\//i.test(value)
      ? `https://${value}`
      : value;
    url = new URL(normalizedUrl);
  } catch {
    return { ok: false, error: "Enter a numeric FPL Team ID or a valid fantasy.premierleague.com team URL." };
  }

  const hostname = url.hostname.toLowerCase();
  if (url.protocol !== "https:" || !["fantasy.premierleague.com", "www.fantasy.premierleague.com"].includes(hostname)) {
    return { ok: false, error: "For your security, use an official fantasy.premierleague.com team URL." };
  }

  // Official FPL links can include a locale prefix (for example /en/entry/...)
  // and may point to points, history, transfers, or an individual Gameweek.
  const match = url.pathname.match(/(?:^|\/)entry\/(\d+)(?:\/|$)/i);
  if (!match) {
    return { ok: false, error: "That FPL URL does not contain /entry/ followed by a Team ID." };
  }
  return validateTeamId(match[1], "fpl_url");
}
