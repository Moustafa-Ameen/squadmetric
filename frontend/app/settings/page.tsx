"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getTeam } from "@/lib/api";
import { DEFAULT_ONBOARDING_PREFERENCES, persistOnboarding, type OnboardingPreferences } from "@/lib/account";
import { disconnectAccountTeam, exportAccountData, savePreferencePatch } from "@/lib/accountStorage";
import { parseFplTeamInput } from "@/lib/fplTeam";
import { parseReviewMode } from "@/lib/reviewMode";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import type { ReviewMode } from "@/lib/reviewMode";
import type { TeamData } from "@/lib/types";

export default function SettingsPage() {
  const router = useRouter();
  const [teamId, setTeamId] = useState("");
  const [draftTeamId, setDraftTeamId] = useState("");
  const [team, setTeam] = useState<TeamData | null>(null);
  const [teamError, setTeamError] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showFixtureBar, setShowFixtureBar] = useState(true);
  const [showBench, setShowBench] = useState(true);
  const [compactRows, setCompactRows] = useState(false);
  const [reviewMode, setReviewMode] = useState<ReviewMode>("points");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountMessage, setAccountMessage] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
      setTeamId(savedTeamId);
      setDraftTeamId(savedTeamId);
      setShowFixtureBar(window.localStorage.getItem("show_match_bar") !== "false");
      setShowBench(window.localStorage.getItem("show_bench_players") !== "false");
      setCompactRows(window.localStorage.getItem("compact_table_rows") === "true");
      setReviewMode(parseReviewMode(window.localStorage.getItem("fpl_decision_objective_mode")));
      void createSupabaseBrowserClient()?.auth.getUser().then(({ data }) => setAccountEmail(data.user?.email ?? ""));
    });
  }, []);

  useEffect(() => {
    if (!teamId) {
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
  }, [teamId]);

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
        supabase: createSupabaseBrowserClient(),
        teamId: parsed.value.teamId,
        sourceInput: draftTeamId.trim(),
        team: verified,
        preferences: { ...DEFAULT_ONBOARDING_PREFERENCES, ...stored },
      });
      setTeamId(parsed.value.teamId);
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
    setDraftTeamId("");
    setTeam(null);
  }

  function updateBoolean(
    key: "show_match_bar" | "show_bench_players" | "compact_table_rows",
    value: boolean,
    setter: (value: boolean) => void,
  ) {
    window.localStorage.setItem(key, String(value));
    savePreferencePatch({
      ...(key === "show_match_bar" ? { showFixtureBar: value } : {}),
      ...(key === "show_bench_players" ? { showBenchPlayers: value } : {}),
      ...(key === "compact_table_rows" ? { compactTableRows: value } : {}),
    });
    setter(value);
  }

  function updateReviewMode(value: ReviewMode) {
    window.localStorage.setItem("fpl_decision_objective_mode", value);
    savePreferencePatch({ objectiveMode: value });
    setReviewMode(value);
  }

  async function downloadAccountData() {
    setAccountBusy(true);
    setAccountMessage("");
    try {
      const payload = await exportAccountData();
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `squadmetric-account-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setAccountMessage("Your account export has been downloaded.");
    } catch {
      setAccountMessage("The account export could not be created. Try again.");
    } finally {
      setAccountBusy(false);
    }
  }

  async function deleteAccount() {
    if (deleteConfirmation !== "DELETE") return;
    setAccountBusy(true);
    setAccountMessage("");
    try {
      const response = await fetch("/api/account/delete", { method: "POST" });
      if (!response.ok) throw new Error("delete failed");
      window.localStorage.clear();
      router.replace("/");
      router.refresh();
    } catch {
      setAccountMessage("The account could not be deleted. Your data is unchanged.");
      setAccountBusy(false);
    }
  }

  async function signOut() {
    await createSupabaseBrowserClient()?.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div>
      <SectionHeader title="Settings" subtitle="Account and display preferences" />

      <div className="space-y-6">
        <Panel title="FPL Account">
          <div className="mb-4 rounded-xl border border-violet-200 bg-violet-50 p-4 text-sm leading-6 text-violet-950">
            Connect by Team ID or an official FPL URL in the guided account setup. SquadMetric never asks for your FPL email or password.
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

          {teamId ? (
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

        <Panel title="SquadMetric account">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div><div className="font-semibold text-primary">{accountEmail || "Local development mode"}</div><p className="mt-1 text-sm text-muted">Account data is protected by Supabase row-level security when sign-in is configured.</p></div>
            {accountEmail ? <button type="button" onClick={signOut} className="fpl-secondary-button px-4 py-2 text-sm">Sign out</button> : null}
          </div>
          <div className="mt-5 border-t border-fpl-border pt-5">
            <button type="button" onClick={downloadAccountData} disabled={accountBusy} className="fpl-secondary-button px-4 py-2 text-sm disabled:opacity-50">Download my data</button>
          </div>
          {accountEmail ? (
            <div className="mt-5 rounded-xl border border-rose-300/30 bg-rose-500/5 p-4">
              <div className="font-semibold text-primary">Delete account</div>
              <p className="mt-1 text-sm text-muted">This permanently deletes your SquadMetric account and all linked data. It does not change your official FPL team.</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} placeholder="Type DELETE" className="rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-sm text-primary" />
                <button type="button" onClick={deleteAccount} disabled={deleteConfirmation !== "DELETE" || accountBusy} className="rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">Delete permanently</button>
              </div>
            </div>
          ) : null}
        </Panel>

        <Panel title="Decision objective">
          <div className="flex flex-wrap gap-2">
            <ObjectiveButton active={reviewMode === "points"} label="Points mode (default)" onClick={() => updateReviewMode("points")} />
            <ObjectiveButton active={reviewMode === "rank"} label="Rank review mode" onClick={() => updateReviewMode("rank")} />
          </div>
          <p className="mt-3 text-xs text-muted">Rank mode is an optional post-Gameweek review lens. It does not alter the production points-maximizing transfer, captain, or chip recommendations.</p>
        </Panel>

        <Panel title="Display preferences">
          <div className="space-y-4">
            <Toggle
              label="Show fixture bar"
              checked={showFixtureBar}
              onChange={(value) => updateBoolean("show_match_bar", value, setShowFixtureBar)}
            />
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
            <p>Built with Python, FastAPI, and Next.js</p>
            <p>Live season: 2026/27</p>
            <p>Models: consumer-specific portfolio trained only on completed seasons</p>
            <p>Validation: season-held-out benchmark evidence is shown on the Proof page</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ObjectiveButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${active ? "border-fpl-green bg-fpl-green/15 text-fpl-green" : "border-fpl-border bg-fpl-raised text-secondary"}`}>{label}</button>;
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
