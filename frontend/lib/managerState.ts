export type ManagerStateOverride = {
  bank: number;
  freeTransfers: number;
};

export function managerStateKey(teamId: string): string {
  return `squadmetric_manager_state_v1:${teamId}`;
}

export function readManagerStateOverride(
  teamId: string,
  storage: Pick<Storage, "getItem"> | undefined = browserStorage(),
): ManagerStateOverride | undefined {
  if (!teamId || !storage) return undefined;
  try {
    const parsed = JSON.parse(storage.getItem(managerStateKey(teamId)) ?? "null");
    if (!parsed || typeof parsed !== "object") return undefined;
    const bank = Number(parsed.bank);
    const freeTransfers = Number(parsed.freeTransfers);
    if (!Number.isFinite(bank) || bank < 0 || bank > 20) return undefined;
    if (!Number.isInteger(freeTransfers) || freeTransfers < 0 || freeTransfers > 5) {
      return undefined;
    }
    return { bank, freeTransfers };
  } catch {
    return undefined;
  }
}

export function saveManagerStateOverride(
  teamId: string,
  value: ManagerStateOverride,
  storage: Pick<Storage, "setItem"> | undefined = browserStorage(),
): void {
  if (!teamId || !storage) return;
  storage.setItem(managerStateKey(teamId), JSON.stringify(value));
}

export function clearManagerStateOverride(
  teamId: string,
  storage: Pick<Storage, "removeItem"> | undefined = browserStorage(),
): void {
  if (!teamId || !storage) return;
  storage.removeItem(managerStateKey(teamId));
}

function browserStorage(): Storage | undefined {
  return typeof window === "undefined" ? undefined : window.localStorage;
}
