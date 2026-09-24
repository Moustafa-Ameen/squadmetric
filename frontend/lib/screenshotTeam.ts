import type { Player } from "./types";

export function normalizePlayerName(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function detectPlayersFromOcr(text: string, catalog: Player[]): Player[] {
  const haystack = normalizePlayerName(text);
  const rawAliases = catalog
    .filter((player) => Number(player.element_id) > 0)
    .flatMap((player) => [player.web_name, player.name]
      .filter((name): name is string => Boolean(name))
      .map((name) => ({ alias: normalizePlayerName(name), player })))
    .filter(({ alias }) => alias.length >= 4);
  const aliasOwners = new Map<string, Set<number>>();
  for (const { alias, player } of rawAliases) {
    const owners = aliasOwners.get(alias) ?? new Set<number>();
    owners.add(Number(player.element_id));
    aliasOwners.set(alias, owners);
  }
  const aliases = rawAliases
    .filter(({ alias }) => aliasOwners.get(alias)?.size === 1)
    .sort((a, b) => b.alias.length - a.alias.length);

  const found = new Map<number, Player>();
  const claimed: Array<[number, number]> = [];
  const claimedAliases: string[] = [];
  for (const { alias, player } of aliases) {
    const id = Number(player.element_id);
    if (found.has(id)) continue;
    if (claimedAliases.some((selected) => ` ${selected} `.includes(` ${alias} `))) continue;
    const pattern = new RegExp(`(?:^| )${escapeRegex(alias)}(?= |$)`, "g");
    for (const match of haystack.matchAll(pattern)) {
      const start = (match.index ?? 0) + (match[0].startsWith(" ") ? 1 : 0);
      const end = start + alias.length;
      if (claimed.some(([left, right]) => start < right && end > left)) continue;
      found.set(id, player);
      claimed.push([start, end]);
      claimedAliases.push(alias);
      break;
    }
  }
  return [...found.values()].slice(0, 15);
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
