"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getTeam } from "@/lib/api";
import { DEFAULT_ONBOARDING_PREFERENCES, persistOnboarding, type OnboardingPreferences } from "@/lib/account";
import { disconnectAccountTeam, exportAccountData, isGuestDemoMode, savePreferencePatch } from "@/lib/accountStorage";
import { parseFplTeamInput } from "@/lib/fplTeam";
import type { TeamData } from "@/lib/types";

export default function SettingsPage() {
  const [teamId, setTeamId] = useState("");
  const [guestMode, setGuestMode] = useState(false);
  const [draftTeamId, setDraftTeamId] = useState("");
  const [team, setTeam] = useState<TeamData | null>(null);
  const [teamError, setTeamError] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showBench, setShowBench] = useState(true);
  const [compactRows, setCompactRows] = useState(false);
  const [accountMessage, setAccountMessage] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
      setTeamId(savedTeamId);
      setGuestMode(isGuestDemoMode());
      setDraftTeamId("");
      setShowBench(window.localStorage.getItem("show_bench_players") !== "false");
      setCompactRows(window.localStorage.getItem("compact_table_rows") === "true");
    });
  }, []);

  useEffect(() => {
    if (!teamId || guestMode) {
      queueMicrotask(() => {
        setTeam(null);
        setTeamError(false);
      });
      return;
    }

    let cancelled = false;
    getTeam(teamId)
      .then((data) => {
        if (!cancelled) {
          setTeam(data);
          setTeamError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTeam(null);
          setTeamError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [teamId, guestMode]);

  async function saveTeamId() {
    const parsed = parseFplTeamInput(draftTeamId);
    if (!parsed.ok) {
      setAccountMessage(parsed.error);
      return;
    }
    setAccountBusy(true);
    setAccountMessage("");
    try {
      const verified = await getTeam(parsed.value.teamId);
      const stored = JSON.parse(window.localStorage.getItem("squadmetric_preferences") ?? "{}") as Partial<OnboardingPreferences>;
      await persistOnboarding({
        teamId: parsed.value.teamId,
        preferences: { ...DEFAULT_ONBOARDING_PREFERENCES, ...stored },
      });
      setTeamId(parsed.value.teamId);
      setGuestMode(false);
      setTeam(verified);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch {
      setAccountMessage("That team could not be verified and was not saved.");
    } finally {
      setAccountBusy(false);
    }
  }

  async function disconnect() {
    await disconnectAccountTeam().catch(() => undefined);
    setTeamId("");
    setGuestMode(false);
    setDraftTeamId("");
    setTeam(null);
  }

  function updateBoolean(
    key: "show_bench_players" | "compact_table_rows",
    value: boolean,
    setter: (value: boolean) => void,
  ) {
    window.localStorage.setItem(key, String(value));
    savePreferencePatch({
      ...(key === "show_bench_players" ? { showBenchPlayers: value } : {}),
      ...(key === "compact_table_rows" ? { compactTableRows: value } : {}),
    });
    setter(value);
  }

  async function downloadBrowserData() {
    setAccountBusy(true);
    setAccountMessage("");
    try {
      const payload = await exportAccountData();
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `squadmetric-browser-data-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setAccountMessage("Your browser data has been downloaded.");
    } catch {
      setAccountMessage("The browser data export could not be created. Try again.");
    } finally {
      setAccountBusy(false);
    }
  }

  return (
    <div>
      <SectionHeader title="Settings" subtitle="Team and display preferences" />

      <div className="space-y-6">
        <Panel title="Linked FPL team">
          <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50 p-4 text-sm leading-6 text-violet-950">
            Connect by Team ID or an official FPL URL. SquadMetric never asks for your FPL email or password.
            <Link href="/onboarding" className="ml-1 font-bold text-violet-700 underline decoration-violet-300 underline-offset-2">Open team setup</Link>
          </div>
          <label className="block">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Your FPL Team ID
            </span>
            <div className="mt-2 flex flex-col gap-3 sm:flex-row">
              <input
                value={draftTeamId}
                onChange={(event) => setDraftTeamId(event.target.value)}
                placeholder="Enter team ID"
                className="w-full rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-primary outline-none focus:border-fpl-green sm:max-w-xs"
              />
              <button type="button" onClick={saveTeamId} disabled={accountBusy} className="fpl-button px-4 py-2 text-sm disabled:opacity-50">
                {saved ? "Saved ✓" : accountBusy ? "Verifying…" : "Verify and save"}
              </button>
            </div>
          </label>

          {guestMode ? (
            <div className="mt-4 rounded-[10px] border border-violet-200 bg-violet-50 p-4">
              <div className="inline-flex rounded-full bg-violet-100 px-2.5 py-1 text-xs font-bold text-violet-800">Demo team</div>
              <p className="mt-3 text-sm text-violet-950">You are exploring a dedicated sample squad. Enter your Team ID above to replace it with personalized recommendations.</p>
              <button type="button" onClick={disconnect} className="mt-3 text-sm font-semibold text-fpl-red">Exit demo</button>
            </div>
          ) : teamId ? (
            <div className="mt-4 rounded-[10px] border border-fpl-border bg-fpl-raised p-4">
              {team ? (
                <div>
                  <div className="font-semibold text-primary">{team.team_name}</div>
                  <div className="mt-1 text-sm text-secondary">
                    Overall rank: {team.overall_rank?.toLocaleString() ?? "-"}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted">
                  {teamError ? "Unable to load team preview." : "Loading team preview..."}
                </div>
              )}
              <button type="button" onClick={disconnect} className="mt-3 text-sm font-semibold text-fpl-red">
                Disconnect
              </button>
            </div>
          ) : null}
          {accountMessage ? <p className="mt-3 text-sm text-secondary" role="status">{accountMessage}</p> : null}
        </Panel>

        <Panel title="Data saved on this device">
          <div className="font-semibold text-primary">Browser storage</div>
          <p className="mt-1 text-sm text-muted">Your linked team, drafts, watchlist, and preferences stay in this browser. No SquadMetric account is required.</p>
          <div className="mt-5 border-t border-fpl-border pt-5">
            <button type="button" onClick={downloadBrowserData} disabled={accountBusy} className="fpl-secondary-button px-4 py-2 text-sm disabled:opacity-50">Download my data</button>
          </div>
        </Panel>

        <Panel title="Display preferences">
          <div className="space-y-4">
            <Toggle
              label="Show bench players on squad page"
              checked={showBench}
              onChange={(value) => updateBoolean("show_bench_players", value, setShowBench)}
            />
            <Toggle
              label="Compact table rows"
              checked={compactRows}
              onChange={(value) => updateBoolean("compact_table_rows", value, setCompactRows)}
            />
          </div>
        </Panel>

        <Panel title="About">
          <div className="space-y-1 text-sm text-muted">
            <p>SquadMetric v1.0</p>
            <p>Live season: 2026/27</p>
            <p>Independent FPL analytics. SquadMetric never changes your official team.</p>
            <p><Link href="/proof" className="font-semibold text-violet-700 hover:text-violet-900">How SquadMetric performs →</Link></p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-sm text-primary">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="sr-only"
      />
      <span
        className={`relative h-6 w-11 rounded-full border transition ${
          checked ? "border-fpl-green bg-fpl-green/20" : "border-fpl-border bg-fpl-raised"
        }`}
      >
        <span
          className={`absolute top-1 h-4 w-4 rounded-full transition ${
            checked ? "left-6 bg-fpl-green" : "left-1 bg-muted"
          }`}
        />
      </span>
    </label>
  );
}
