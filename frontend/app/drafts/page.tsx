"use client";

import { Copy, GitCompareArrows, RotateCcw, Save, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { ErrorState, PlannerSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getDraftWorkspace, getSeasonState } from "@/lib/api";
import { persistSavedDrafts, readSavedDrafts } from "@/lib/accountStorage";
import {
  compareDraft,
  draftChanges,
  draftRating,
  normalizedDraftPosition,
  selectDraftLineup,
  validateDraft,
} from "@/lib/draftWorkspace";
import type {
  DraftHorizon,
  DraftRiskProfile,
  SavedDraft,
} from "@/lib/draftWorkspace";
import { points } from "@/lib/format";
import type {
  DraftWorkspacePlayer,
  DraftWorkspaceResponse,
  SeasonState,
} from "@/lib/types";

type Horizon = DraftHorizon;
type RiskProfile = DraftRiskProfile;

export default function DraftWorkspacePage() {
  const [horizon, setHorizon] = useState<Horizon>(8);
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [workspace, setWorkspace] = useState<DraftWorkspaceResponse | null>(null);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [drafts, setDrafts] = useState<SavedDraft[]>([]);
  const [activeDraftId, setActiveDraftId] = useState("");
  const [draftName, setDraftName] = useState("Optimizer draft");
  const [playerIds, setPlayerIds] = useState<number[]>([]);
  const [selectedOutgoingId, setSelectedOutgoingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      setLoading(true);
      setError(false);
    });
    getSeasonState()
      .then(async (state) => {
        if (cancelled) return;
        setSeasonState(state);
        if (!state.recommendations_ready) return;
        const response = await getDraftWorkspace(horizon, riskProfile);
        if (cancelled) return;
        setWorkspace(response);
        const optimizedIds = response.optimized.squad.map((player) => player.element_id);
        const stored = readSavedDrafts().filter((draft) => draft.bootstrapHash === response.bootstrap_hash);
        setDrafts(stored);
        const first = stored[0];
        setActiveDraftId(first?.id ?? "");
        setDraftName(first?.name ?? "Optimizer draft");
        setPlayerIds(first?.playerIds ?? optimizedIds);
        setSelectedOutgoingId(null);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [horizon, riskProfile]);

  const playerById = useMemo(
    () => new Map(workspace?.player_pool.map((player) => [player.element_id, player]) ?? []),
    [workspace],
  );
  const squad = useMemo(
    () => playerIds.map((id) => playerById.get(id)).filter(isPlayer),
    [playerById, playerIds],
  );
  const optimizedSquad = useMemo(
    () =>
      (workspace?.optimized.squad ?? [])
        .map((player) => playerById.get(player.element_id))
        .filter(isPlayer),
    [playerById, workspace],
  );
  const validation = useMemo(
    () => (workspace ? validateDraft(squad, workspace.constraints) : null),
    [squad, workspace],
  );
  const lineup = useMemo(() => selectDraftLineup(squad), [squad]);
  const rating = useMemo(
    () => draftRating(squad, optimizedSquad, validation?.legal ?? false),
    [optimizedSquad, squad, validation],
  );
  const comparisonRows = useMemo(() => {
    if (!workspace) return [];
    const rows = [
      compareDraft(
        {
          id: "optimizer",
          name: "Optimizer control",
          playerIds: workspace.optimized.squad.map((player) => player.element_id),
        },
        workspace.player_pool,
        workspace.constraints,
      ),
      ...drafts.map((draft) =>
        compareDraft(draft, workspace.player_pool, workspace.constraints),
      ),
      compareDraft(
        { id: "workspace", name: "Current workspace", playerIds },
        workspace.player_pool,
        workspace.constraints,
      ),
    ];
    return rows.sort((a, b) => b.planningValue - a.planningValue);
  }, [drafts, playerIds, workspace]);
  const selectedOutgoing = selectedOutgoingId ? playerById.get(selectedOutgoingId) : null;
  const selectedSet = useMemo(() => new Set(playerIds), [playerIds]);
  const candidates = useMemo(() => {
    if (!workspace || !selectedOutgoing) return [];
    const needle = search.trim().toLowerCase();
    return workspace.player_pool
      .filter(
        (player) =>
          !selectedSet.has(player.element_id) &&
          normalizedDraftPosition(player.position) === normalizedDraftPosition(selectedOutgoing.position) &&
          (!needle || `${player.name} ${player.web_name ?? ""} ${player.team}`.toLowerCase().includes(needle)),
      )
      .sort((a, b) => b.horizon_points - a.horizon_points)
      .slice(0, 40);
  }, [search, selectedOutgoing, selectedSet, workspace]);

  if (loading) return <PlannerSkeleton />;
  if (error) return <ErrorState />;
  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Draft Workspace" subtitle="Opening-squad editing is paused until current data passes validation" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }
  if (!workspace || !validation) return <ErrorState />;

  function replacePlayer(incoming: DraftWorkspacePlayer) {
    if (!selectedOutgoingId) return;
    const nextIds = playerIds.map((id) => (id === selectedOutgoingId ? incoming.element_id : id));
    const nextSquad = nextIds.map((id) => playerById.get(id)).filter(isPlayer);
    if (!validateDraft(nextSquad, workspace!.constraints).legal) return;
    setPlayerIds(nextIds);
    setSelectedOutgoingId(null);
    setSearch("");
  }

  function saveCurrentDraft() {
    const existing = drafts.find((draft) => draft.id === activeDraftId);
    const now = new Date().toISOString();
    const name = draftName.trim() || existing?.name || `Draft ${drafts.length + 1}`;
    const saved: SavedDraft = {
      schemaVersion: 2,
      id: existing?.id ?? crypto.randomUUID(),
      name,
      playerIds,
      bootstrapHash: workspace!.bootstrap_hash,
      fixturesHash: workspace!.fixtures_hash ?? null,
      rulesVersion: workspace!.rules_version,
      horizon,
      riskProfile,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    };
    const next = existing
      ? drafts.map((draft) => (draft.id === existing.id ? saved : draft))
      : [...drafts, saved];
    persistSavedDrafts(next);
    setDrafts(next);
    setActiveDraftId(saved.id);
    setDraftName(saved.name);
  }

  function duplicateDraft() {
    const copy: SavedDraft = {
      schemaVersion: 2,
      id: crypto.randomUUID(),
      name: `Draft ${drafts.length + 1}`,
      playerIds: [...playerIds],
      bootstrapHash: workspace!.bootstrap_hash,
      fixturesHash: workspace!.fixtures_hash ?? null,
      rulesVersion: workspace!.rules_version,
      horizon,
      riskProfile,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    const next = [...drafts, copy];
    persistSavedDrafts(next);
    setDrafts(next);
    setActiveDraftId(copy.id);
    setDraftName(copy.name);
  }

  function deleteDraft() {
    if (!activeDraftId) return;
    const next = drafts.filter((draft) => draft.id !== activeDraftId);
    persistSavedDrafts(next);
    setDrafts(next);
    const first = next[0];
    setActiveDraftId(first?.id ?? "");
    setDraftName(first?.name ?? "Optimizer draft");
    setPlayerIds(first?.playerIds ?? workspace!.optimized.squad.map((player) => player.element_id));
  }

  function selectDraft(id: string) {
    const selected = drafts.find((draft) => draft.id === id);
    setActiveDraftId(id);
    setDraftName(selected?.name ?? "Optimizer draft");
    setPlayerIds(selected?.playerIds ?? workspace!.optimized.squad.map((player) => player.element_id));
    setSelectedOutgoingId(null);
  }

  const starters = lineup.startingIds.map((id) => playerById.get(id)).filter(isPlayer);
  const bench = lineup.benchIds.map((id) => playerById.get(id)).filter(isPlayer);

  return (
    <div className="space-y-5">
      <SectionHeader
        title={`${workspace.season} Draft Workspace`}
        subtitle="Build, validate, compare, and save legal opening squads without an FPL Team ID"
      />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.12em] text-fpl-green">Rules-aware squad builder</div>
            <h2 className="mt-2 text-xl font-semibold text-primary">
              {validation.legal ? "Legal draft" : "Draft needs attention"} · Rating score {rating}
            </h2>
            <p className="mt-2 text-sm text-secondary">
              The optimizer is the starting point. Every replacement is checked against the live budget,
              position counts, and three-per-club rule.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="draft-name">Draft name</label>
            <input
              id="draft-name"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              className="w-40 rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-sm text-primary outline-none focus:border-fpl-green"
              aria-label="Draft name"
            />
            <select
              value={activeDraftId}
              onChange={(event) => selectDraft(event.target.value)}
              className="rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-sm text-primary"
              aria-label="Select saved draft"
            >
              <option value="">Unsaved optimizer draft</option>
              {drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.name}</option>)}
            </select>
            <Action icon={<Save className="h-4 w-4" />} label="Save" onClick={saveCurrentDraft} />
            <Action icon={<Copy className="h-4 w-4" />} label="Duplicate" onClick={duplicateDraft} />
            <Action icon={<Trash2 className="h-4 w-4" />} label="Delete" onClick={deleteDraft} disabled={!activeDraftId} />
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Cost" value={`£${validation.cost.toFixed(1)}m`} />
          <Metric label="Bank" value={`£${validation.bank.toFixed(1)}m`} good={validation.bank >= 0} />
          <Metric label="GW1 incl. captain" value={`${points(lineup.expectedGw1Points)} pts`} />
          <Metric label="Formation" value={lineup.formation} />
          <Metric label="Bench availability" value={`${Math.round(lineup.benchStartProbability * 100)}%`} />
        </div>
        {!validation.legal ? (
          <ul className="mt-4 list-disc space-y-1 rounded-lg border border-fpl-red/30 bg-fpl-red/10 p-4 pl-8 text-sm text-fpl-red">
            {validation.errors.map((message) => <li key={message}>{message}</li>)}
          </ul>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
            {([3, 5, 8] as Horizon[]).map((option) => (
              <button key={option} type="button" onClick={() => setHorizon(option)} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${horizon === option ? "bg-fpl-green text-fpl-dark" : "text-secondary"}`}>
                {option} GWs
              </button>
            ))}
          </div>
          <select value={riskProfile} onChange={(event) => setRiskProfile(event.target.value as RiskProfile)} className="rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-xs text-primary" aria-label="Draft risk profile">
            <option value="balanced">Balanced optimizer</option>
            <option value="maximum_points">Maximum points</option>
            <option value="safe">Safer depth</option>
          </select>
          <button type="button" onClick={() => setPlayerIds(workspace.optimized.squad.map((player) => player.element_id))} className="inline-flex items-center gap-2 rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-xs font-semibold text-primary">
            <RotateCcw className="h-4 w-4" /> Reset to optimizer
          </button>
        </div>
      </Panel>

      <Panel>
        <div className="flex items-start gap-3">
          <span className="rounded-lg border border-fpl-green/30 bg-fpl-green/10 p-2 text-fpl-green">
            <GitCompareArrows className="h-4 w-4" />
          </span>
          <div>
            <h2 className="text-base font-semibold text-primary">Multi-draft comparison</h2>
            <p className="mt-1 text-xs text-muted">
              Compare the optimizer, every saved draft, and your unsaved workspace on the same current projections.
              Planning value includes the projected XI, captain, and a small availability-weighted autosub allowance.
            </p>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto" role="region" aria-label="Draft comparison table" tabIndex={0}>
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="border-b border-fpl-border text-[10px] uppercase tracking-[0.08em] text-muted">
              <tr><th className="px-3 py-2">Draft</th><th className="px-3 py-2">Plan value</th><th className="px-3 py-2">GW1</th><th className="px-3 py-2">Bank</th><th className="px-3 py-2">Availability</th><th className="px-3 py-2">Changes vs control</th><th className="px-3 py-2">Status</th></tr>
            </thead>
            <tbody>
              {comparisonRows.map((row, index) => {
                const changes = draftChanges(
                  workspace.optimized.squad.map((player) => player.element_id),
                  row.playerIds,
                );
                const incoming = changes.playersIn
                  .map((id) => playerById.get(id)?.web_name ?? playerById.get(id)?.name)
                  .filter(Boolean);
                const staleDraft = row.id !== "optimizer" && row.id !== "workspace"
                  ? drafts.find((draft) => draft.id === row.id)?.fixturesHash !== (workspace.fixtures_hash ?? null)
                  : false;
                return (
                  <tr key={row.id} className="border-b border-fpl-border/60 last:border-0">
                    <td className="px-3 py-3"><span className="font-semibold text-primary">{index + 1}. {row.name}</span><span className="mt-0.5 block text-[11px] text-muted">{row.formation} · £{row.cost.toFixed(1)}m</span></td>
                    <td className="px-3 py-3 font-mono font-bold text-fpl-green">{row.planningValue.toFixed(1)}</td>
                    <td className="px-3 py-3 font-mono text-primary">{points(row.expectedGw1Points)}</td>
                    <td className="px-3 py-3 font-mono text-primary">£{row.bank.toFixed(1)}m</td>
                    <td className="px-3 py-3"><span className="text-primary">{Math.round(row.averageStartLikelihood * 100)}%</span><span className="block text-[11px] text-muted">{row.lowReliabilityCount} below 75%</span></td>
                    <td className="max-w-[260px] px-3 py-3 text-xs text-secondary">{incoming.length ? `IN ${incoming.join(", ")}` : "Same 15"}</td>
                    <td className="px-3 py-3"><span className={row.legal ? "text-fpl-green" : "text-fpl-red"}>{row.legal ? "Legal" : "Invalid"}</span>{staleDraft ? <span className="block text-[10px] text-fpl-yellow">Recalculated after fixture change</span> : null}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <Panel>
          <h2 className="text-base font-semibold text-primary">Your 15-player squad</h2>
          <p className="mt-1 text-xs text-muted">Select a player to see legal same-position replacements.</p>
          <div className="mt-4 space-y-5">
            {(["GKP", "DEF", "MID", "FWD"] as const).map((position) => (
              <div key={position}>
                <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">{position}</div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {squad.filter((player) => normalizedDraftPosition(player.position) === position).map((player) => (
                    <PlayerButton key={player.element_id} player={player} selected={selectedOutgoingId === player.element_id} onClick={() => setSelectedOutgoingId(player.element_id)} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel>
          <h2 className="text-base font-semibold text-primary">Replacement finder</h2>
          {selectedOutgoing ? (
            <>
              <p className="mt-1 text-xs text-secondary">Replacing {selectedOutgoing.web_name ?? selectedOutgoing.name} · {normalizedDraftPosition(selectedOutgoing.position)}</p>
              <label className="mt-4 flex items-center gap-2 rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2">
                <Search className="h-4 w-4 text-muted" />
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search player or club" className="min-w-0 flex-1 bg-transparent text-sm text-primary outline-none" />
              </label>
              <div className="mt-3 max-h-[520px] space-y-2 overflow-y-auto pr-1">
                {candidates.map((candidate) => {
                  const next = squad.map((player) => player.element_id === selectedOutgoing.element_id ? candidate : player);
                  const legal = validateDraft(next, workspace.constraints).legal;
                  return (
                    <button key={candidate.element_id} type="button" disabled={!legal} onClick={() => replacePlayer(candidate)} className="flex w-full items-center justify-between gap-3 rounded-lg border border-fpl-border bg-fpl-raised p-3 text-left disabled:cursor-not-allowed disabled:opacity-35">
                      <span className="min-w-0"><span className="block truncate text-sm font-semibold text-primary">{candidate.web_name ?? candidate.name}</span><span className="mt-1 block text-[11px] text-muted">{candidate.team} · £{candidate.price.toFixed(1)}m · {Math.round(candidate.start_likelihood * 100)}% start</span></span>
                      <span className="shrink-0 text-right font-mono text-xs text-fpl-green">{points(candidate.gw1_points)}<span className="block text-[10px] text-muted">{candidate.horizon_points.toFixed(1)} horizon</span></span>
                    </button>
                  );
                })}
              </div>
            </>
          ) : <p className="mt-4 rounded-lg border border-dashed border-fpl-border p-4 text-sm text-muted">Select a squad player first.</p>}
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <LineupPanel title={`Best XI · ${lineup.formation}`} players={starters} captainId={lineup.captainId} viceCaptainId={lineup.viceCaptainId} />
        <LineupPanel title="Autosub bench order" players={bench} captainId={null} viceCaptainId={null} />
      </div>

      <p className="text-[11px] text-muted">{workspace.model} · {workspace.rules_version} · cutoff {workspace.data_cutoff} · {workspace.bootstrap_hash.slice(0, 12)}</p>
    </div>
  );
}

function PlayerButton({ player, selected, onClick }: { player: DraftWorkspacePlayer; selected: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`rounded-lg border p-3 text-left ${selected ? "border-fpl-green bg-fpl-green/10" : "border-fpl-border bg-fpl-raised"}`}>
      <div className="flex items-start justify-between gap-2"><span className="truncate font-semibold text-primary">{player.web_name ?? player.name}</span><span className="font-mono text-xs text-fpl-green">{points(player.gw1_points)}</span></div>
      <div className="mt-1 text-[11px] text-muted">{player.team} · £{player.price.toFixed(1)}m · {player.horizon_points.toFixed(1)} horizon</div>
    </button>
  );
}

function LineupPanel({ title, players, captainId, viceCaptainId }: { title: string; players: DraftWorkspacePlayer[]; captainId: number | null; viceCaptainId: number | null }) {
  return (
    <Panel><h2 className="text-base font-semibold text-primary">{title}</h2><div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{players.map((player, index) => <div key={player.element_id} className="rounded-lg border border-fpl-border bg-fpl-raised p-3"><div className="flex justify-between gap-2"><span className="font-semibold text-primary">{index + 1}. {player.web_name ?? player.name}{captainId === player.element_id ? " (C)" : viceCaptainId === player.element_id ? " (VC)" : ""}</span><span className="font-mono text-xs text-fpl-green">{points(player.gw1_points)}</span></div><div className="mt-1 text-[11px] text-muted">{player.team} · {normalizedDraftPosition(player.position)} · {Math.round(player.start_likelihood * 100)}% start</div></div>)}</div></Panel>
  );
}

function Metric({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3"><div className="text-[10px] uppercase tracking-[0.08em] text-muted">{label}</div><div className={`mt-1 font-mono text-base font-bold ${good ? "text-fpl-green" : "text-primary"}`}>{value}</div></div>;
}

function Action({ icon, label, onClick, disabled }: { icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled} className="inline-flex items-center gap-2 rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-xs font-semibold text-primary disabled:opacity-40">{icon}{label}</button>;
}

function isPlayer(player: DraftWorkspacePlayer | undefined): player is DraftWorkspacePlayer {
  return player !== undefined;
}
