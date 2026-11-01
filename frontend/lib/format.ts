export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function points(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

export function price(value: number | null | undefined): string {
  return `£${points(value)}m`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

export function timeAgo(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours) || hours < 0) return "-";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours < 48) {
    const whole = Math.round(hours);
    return `${whole} hour${whole === 1 ? "" : "s"} ago`;
  }
  return `${Math.round(hours / 24)} days ago`;
}

export function positionCode(position: string): string {
  const map: Record<string, string> = {
    Goalkeeper: "GK",
    Defender: "DEF",
    Midfielder: "MID",
    Forward: "FWD",
    GKP: "GK",
  };
  return map[position] ?? position;
}

const TEAM_CODES: Record<string, number> = {
  Arsenal: 3,
  ARS: 3,
  "Aston Villa": 7,
  AVL: 7,
  Burnley: 90,
  BUR: 90,
  Bournemouth: 91,
  BOU: 91,
  Brentford: 94,
  BRE: 94,
  Brighton: 36,
  BHA: 36,
  Chelsea: 8,
  CHE: 8,
  "Crystal Palace": 31,
  CRY: 31,
  Everton: 11,
  EVE: 11,
  Fulham: 54,
  FUL: 54,
  Leeds: 2,
  LEE: 2,
  Liverpool: 14,
  LIV: 14,
  "Man City": 43,
  MCI: 43,
  "Man Utd": 1,
  "Man United": 1,
  MUN: 1,
  Newcastle: 4,
  NEW: 4,
  "Nott'm Forest": 17,
  "Nottingham Forest": 17,
  NFO: 17,
  Sunderland: 56,
  SUN: 56,
  Spurs: 6,
  Tottenham: 6,
  TOT: 6,
  "West Ham": 21,
  WHU: 21,
  Wolves: 39,
  WOL: 39,
};

const TEAM_FULL_NAMES: Record<string, string> = {
  ARS: "Arsenal",
  AVL: "Aston Villa",
  BUR: "Burnley",
  BOU: "Bournemouth",
  BRE: "Brentford",
  BHA: "Brighton",
  CHE: "Chelsea",
  CRY: "Crystal Palace",
  EVE: "Everton",
  FUL: "Fulham",
  LEE: "Leeds",
  LIV: "Liverpool",
  MCI: "Man City",
  MUN: "Man Utd",
  NEW: "Newcastle",
  NFO: "Nott'm Forest",
  SUN: "Sunderland",
  TOT: "Spurs",
  WHU: "West Ham",
  WOL: "Wolves",
};

const PLAYER_TEAM_OVERRIDES: Record<string, { team: string; short: string; code: number }> = {
  "marc guehi": { team: "Crystal Palace", short: "CRY", code: 31 },
  "marc guéhi": { team: "Crystal Palace", short: "CRY", code: 31 },
  "antoine semenyo": { team: "Bournemouth", short: "BOU", code: 91 },
  "james garner": { team: "Everton", short: "EVE", code: 11 },
};

const PLAYER_NAME_OVERRIDES: Record<string, string> = {
  "david raya martin": "David Raya",
  "david raya martín": "David Raya",
  "bruno borges fernandes": "Bruno Fernandes",
  "gabriel dos santos magalhaes": "Gabriel",
  "gabriel dos santos magalhães": "Gabriel",
  "joao pedro junqueira de jesus": "João Pedro",
  "joão pedro junqueira de jesus": "João Pedro",
  "marcos senesi baron": "Marcos Senesi",
  "marcos senesi barón": "Marcos Senesi",
};

export function normalized(value: string | null | undefined): string {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function matchesPlayerSearch(
  query: string | null | undefined,
  ...values: (string | null | undefined)[]
): boolean {
  const term = normalized(query);
  return !term || values.some((value) => normalized(value).includes(term));
}

export function displayPlayerName(name: string, webName?: string | null): string {
  const override = PLAYER_NAME_OVERRIDES[normalized(name)] ?? PLAYER_NAME_OVERRIDES[(name ?? "").toLowerCase()];
  if (override) return override;
  if (webName && !/^[A-Z]\./.test(webName)) return webName;
  return name;
}

export function displayTeam(team?: string | null, playerName?: string | null): string {
  const override = PLAYER_TEAM_OVERRIDES[normalized(playerName)] ?? PLAYER_TEAM_OVERRIDES[(playerName ?? "").toLowerCase()];
  return override?.team ?? TEAM_FULL_NAMES[team ?? ""] ?? team ?? "";
}

export function displayTeamShort(team?: string | null, playerName?: string | null): string {
  const override = PLAYER_TEAM_OVERRIDES[normalized(playerName)] ?? PLAYER_TEAM_OVERRIDES[(playerName ?? "").toLowerCase()];
  if (override) return override.short;
  return team ?? "";
}

export function teamCodeFor(team?: string | null, playerName?: string | null, fallback?: number | null): number {
  const override = PLAYER_TEAM_OVERRIDES[normalized(playerName)] ?? PLAYER_TEAM_OVERRIDES[(playerName ?? "").toLowerCase()];
  if (override) return override.code;
  if (team && TEAM_CODES[team]) return TEAM_CODES[team];
  return fallback ?? 1;
}

export function kitUrl(teamCode?: number | null, team?: string | null, playerName?: string | null): string {
  return `https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCodeFor(team, playerName, teamCode)}-66.png`;
}
