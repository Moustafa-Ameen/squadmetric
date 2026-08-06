"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getTeam } from "@/lib/api";
import type { TeamData } from "@/lib/types";

export default function SettingsPage() {
  const [teamId, setTeamId] = useState("");
  const [draftTeamId, setDraftTeamId] = useState("");
  const [team, setTeam] = useState<TeamData | null>(null);
  const [teamError, setTeamError] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showFixtureBar, setShowFixtureBar] = useState(true);
  const [showBench, setShowBench] = useState(true);
  const [compactRows, setCompactRows] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
      setTeamId(savedTeamId);
      setDraftTeamId(savedTeamId);
      setShowFixtureBar(window.localStorage.getItem("show_match_bar") !== "false");
      setShowBench(window.localStorage.getItem("show_bench_players") !== "false");
      setCompactRows(window.localStorage.getItem("compact_table_rows") === "true");
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

  function saveTeamId() {
    const clean = draftTeamId.trim();
    if (!clean) return;
    window.localStorage.setItem("fpl_team_id", clean);
    setTeamId(clean);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  function disconnect() {
    window.localStorage.removeItem("fpl_team_id");
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
    setter(value);
  }

  return (
    <div>
      <SectionHeader title="Settings" subtitle="Account and display preferences" />

      <div className="space-y-6">
        <Panel title="FPL Account">
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
              <button type="button" onClick={saveTeamId} className="fpl-button px-4 py-2 text-sm">
                {saved ? "Saved ✓" : "Save"}
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
            <p>FPL Intelligence v1.0</p>
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
