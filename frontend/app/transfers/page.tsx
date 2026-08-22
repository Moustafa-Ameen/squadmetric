"use client";

import { ArrowRight, ChevronDown, Info, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/LoadingState";
import { DecisionStatusNotice, SquadScopeNotice } from "@/components/DecisionStatusNotice";
import { Panel } from "@/components/Panel";
import { isSeasonEndedState, SeasonTransitionNotice } from "@/components/SeasonTransitionNotice";
import { SectionHeader } from "@/components/SectionHeader";
import { StartLikelihood } from "@/components/StartLikelihood";
import { useDrawer } from "@/context/DrawerContext";
import { apiErrorCode, getCaptaincyPredictions, getCurrentGameweek, getPlayers, getSeasonState, getSquad, getTeam } from "@/lib/api";
import { squadAccessState } from "@/lib/decisionState";
import { displayPlayerName, displayTeam, kitUrl, normalized, points, positionCode, price } from "@/lib/format";
import { playerXp, selectCurrentSquadMetrics } from "@/lib/squadMetrics";
import type { CaptainPick, Player, SeasonState, SquadPlayer, TeamData } from "@/lib/types";

type Tab = "best" | "prices";
type PositionFilter = "All" | "GK" | "DEF" | "MID" | "FWD";
type Candidate = Player & Pick<CaptainPick, "raw_xp" | "expected_points" | "start_adjusted_xp" | "captain_expected_points" | "captaincy_score" | "projection_contract_version">;

const positionFilters: PositionFilter[] = ["All", "GK", "DEF", "MID", "FWD"];

export default function TransfersPage() {
  const { openDrawer } = useDrawer();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [team, setTeam] = useState<TeamData | null>(null);
  const [teamConnected, setTeamConnected] = useState(false);
  const [savedTeamId, setSavedTeamId] = useState("");
  const [squadErrorCode, setSquadErrorCode] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("best");
  const [position, setPosition] = useState<PositionFilter>("All");
  const [expanded, setExpanded] = useState(false);
  const [showDefconInfo, setShowDefconInfo] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);

  useEffect(() => {
    const teamId = window.localStorage.getItem("fpl_team_id");
    queueMicrotask(() => setSavedTeamId(teamId ?? ""));

    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        if (isSeasonEndedState(state.season_state) || !state.recommendations_ready) return null;
        return Promise.all([
          Promise.all([
            getPlayers({ limit: 1000, sort_by: "transfer_rank_score" }),
            getCaptaincyPredictions(),
          ]).then(([ranked, projected]) => mergeCandidateProjections(ranked, projected)),
          teamId
            ? getCurrentGameweek()
                .then((gw) => getSquad(teamId, gw.current_gw ?? 1))
                .catch((error: unknown) => {
                  setSquadErrorCode(apiErrorCode(error));
                  return [];
                })
            : Promise.resolve([]),
          teamId ? getTeam(teamId).catch(() => null) : Promise.resolve(null),
        ]);
      })
      .then((result) => {
        if (!result) return;
        const [playerRows, squadRows, teamData] = result;
        setCandidates(playerRows);
        setSquad(squadRows);
        setTeam(teamData);
        setTeamConnected(squadRows.length > 0);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const squadKeys = useMemo(() => new Set(squad.map(playerKey)), [squad]);
  const squadState = squadAccessState(savedTeamId, squad.length, squadErrorCode, false);
  const squadMetrics = useMemo(() => selectCurrentSquadMetrics(squad), [squad]);
  const displayedSquad = useMemo(() => [...squadMetrics.starters, ...squadMetrics.bench], [squadMetrics]);
  const upgradeGroups = useMemo(
    () => buildUpgradeGroups(displayedSquad, candidates, squadKeys),
    [candidates, displayedSquad, squadKeys],
  );
  const visibleUpgradeGroups = useMemo(
    () => upgradeGroups.filter((group) => position === "All" || group.position === position),
    [position, upgradeGroups],
  );
  const renderedUpgradeGroups = useMemo(
    () =>
      visibleUpgradeGroups.map((group) => ({
        ...group,
        replacements: group.replacements.slice(0, expanded ? 3 : position === "All" ? 1 : 2),
      })),
    [expanded, position, visibleUpgradeGroups],
  );
  const topTargets = useMemo(
    () =>
      [...candidates]
        .filter((player) => !squadKeys.has(playerKey(player)))
        .sort((a, b) => (b.transfer_rank_score ?? 0) - (a.transfer_rank_score ?? 0))
        .slice(0, 15),
    [candidates, squadKeys],
  );
  const risers = useMemo(() => buildRisers(candidates), [candidates]);
  const fallers = useMemo(() => buildFallers(candidates, new Set(risers.map((player) => player.name))), [candidates, risers]);

  if (loading) return <TableSkeleton />;
  if (error) return <ErrorState />;
  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Who should I bring in?" subtitle="Transfer recommendations are not decision-ready" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }
  if (seasonState && isSeasonEndedState(seasonState.season_state)) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Who should I bring in?" subtitle="Transfer recommendations are paused between seasons" />
        <SeasonTransitionNotice seasonState={seasonState} />
      </div>
    );
  }
  if (!candidates.length) return <EmptyState />;

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Who should I bring in?"
        subtitle={teamConnected ? "Squad-aware upgrades, top targets, and price movement signals." : "Generic targets only until your squad is available."}
      />
      <SquadScopeNotice state={squadState} />

      <div className="rounded-xl border border-fpl-border bg-[linear-gradient(135deg,rgba(0,255,135,0.08),rgba(255,255,255,0.025))] p-4 text-sm text-secondary shadow-[0_16px_40px_rgba(0,0,0,0.26)]">
        Remember: transfers beyond your free allowance cost <span className="font-mono text-fpl-red">-4 pts</span>{" "}
        each.{" "}
        {team?.free_transfers_available !== null && team?.free_transfers_available !== undefined
          ? `You have ${team.free_transfers_available} free transfer(s) available.`
          : "Check the FPL app for your free transfer count."}
      </div>

      <div className="flex w-fit rounded-lg border border-fpl-border bg-fpl-raised p-1">
        <Toggle active={tab === "best"} onClick={() => setTab("best")}>
          Best to sign
        </Toggle>
        <Toggle active={tab === "prices"} onClick={() => setTab("prices")}>
          Price movers
        </Toggle>
      </div>

      {tab === "best" ? (
        <div className="space-y-6">
          {teamConnected ? (
            <Panel>
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-[18px] font-semibold text-primary">Upgrade your squad</h2>
                  <p className="mt-1 text-[13px] text-secondary">
                    One outgoing player per position, with higher-projected replacements from the full player pool.
                  </p>
                </div>
                <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
                  {positionFilters.map((item) => (
                    <Toggle key={item} active={position === item} onClick={() => setPosition(item)}>
                      {item}
                    </Toggle>
                  ))}
                </div>
              </div>

              <div className="space-y-5">
                {renderedUpgradeGroups.map((group) => (
                  <div key={group.position} className="rounded-xl border border-white/[0.06] bg-black/10 p-3">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-muted">
                          {group.position} upgrade
                        </h3>
                        {group.outgoing ? (
                          <p className="mt-1 text-sm text-secondary">
                            Outgoing benchmark:{" "}
                            <span className="font-semibold text-primary">
                              {displayPlayerName(group.outgoing.name, group.outgoing.web_name)}
                            </span>{" "}
                            <span className="text-muted">
                              ({displayTeam(group.outgoing.team, group.outgoing.name)}, {points(predicted(group.outgoing))} pts)
                            </span>
                          </p>
                        ) : null}
                      </div>
                    </div>

                    {group.replacements.length ? (
                      <div className="space-y-3">
                        {group.replacements.map((upgrade) => (
                          <UpgradeRow
                            key={`${group.position}-${upgrade.outgoing.name}-${upgrade.incoming.name}`}
                            upgrade={upgrade}
                            onSelect={openDrawer}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="rounded-lg border border-fpl-border bg-[#161616] p-4 text-sm text-muted">
                        No higher-projected {group.position} replacement is close enough in price right now.
                      </p>
                    )}
                  </div>
                ))}

                <button
                  type="button"
                  onClick={() => setExpanded((value) => !value)}
                  className="inline-flex items-center gap-1 text-sm font-semibold text-fpl-green hover:text-primary"
                >
                  {expanded ? "Show fewer options" : "See more options"}
                  <ChevronDown className={`h-4 w-4 transition ${expanded ? "rotate-180" : ""}`} />
                </button>
              </div>
            </Panel>
          ) : (
            <Panel>
              <p className="text-sm text-muted">
                {savedTeamId
                  ? "Your Team ID is saved, but its squad is unavailable. Squad-relative upgrades are hidden."
                  : "Save your FPL Team ID in Settings to see upgrades from your actual squad."}
              </p>
            </Panel>
          )}

          <Panel>
            <div className="mb-4">
              <h2 className="text-[18px] font-semibold text-primary">Top picks regardless of squad</h2>
              <p className="mt-1 text-[13px] text-secondary">
                Top 15 by transfer score. Signal replaces the old flat trend line.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-muted">
                  <tr>
                    <th className="pb-3 pr-3">Kit</th>
                    <th className="pb-3 pr-3">Player</th>
                    <th className="pb-3 pr-3">Team</th>
                    <th className="pb-3 pr-3">Pos</th>
                    <th className="pb-3 pr-3 text-right">Price</th>
                    <th className="pb-3 pr-3 text-right">Predicted</th>
                    <th className="pb-3 pr-3 text-right">Start %</th>
                    <th className="pb-3 pr-3 text-right">Ownership</th>
                    <th className="pb-3 pr-3 text-right">DefCon / 90</th>
                    <th className="pb-3 text-right">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {topTargets.map((player, index) => (
                    <tr
                      key={player.name}
                      onClick={() => openDrawer(player.name)}
                      className={`cursor-pointer border-b border-fpl-border hover:bg-fpl-green/5 ${
                        index % 2 === 0 ? "bg-[#161616]" : "bg-[#181818]"
                      }`}
                    >
                      <td className="py-3 pr-3">
                        <img
                          src={kitUrl(player.team_code, player.team, player.name)}
                          alt={`${displayTeam(player.team, player.name)} kit`}
                          className="h-10 w-10 object-contain"
                        />
                      </td>
                      <td className="py-3 pr-3 font-semibold text-primary">
                        {displayPlayerName(player.name, player.web_name)}
                        {player.start_likelihood < 0.4 ? (
                          <span className="ml-2 rounded bg-fpl-amber/15 px-2 py-1 text-[11px] text-fpl-amber">
                            rotation risk
                          </span>
                        ) : null}
                      </td>
                      <td className="py-3 pr-3 text-muted">{displayTeam(player.team, player.name)}</td>
                      <td className="py-3 pr-3 text-muted">{positionCode(player.position)}</td>
                      <td className="py-3 pr-3 text-right font-mono text-primary">{price(player.price)}</td>
                      <td className="py-3 pr-3 text-right font-mono text-fpl-green">{points(projected(player))}</td>
                      <td className="py-3 pr-3 text-right">
                        <StartLikelihood value={player.start_likelihood} />
                      </td>
                      <td className="py-3 pr-3 text-right font-mono text-primary">
                        {points(player.selected_by_percent, 0)}%
                      </td>
                      <td className="py-3 pr-3 text-right font-mono text-secondary">
                        {positionCode(player.position) === "GK"
                          ? "-"
                          : points(player.defensive_contribution_per_90)}
                      </td>
                      <td className="py-3 text-right">
                        <TransferSignal player={player} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel>
            <button
              type="button"
              onClick={() => setShowDefconInfo((value) => !value)}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <span className="flex items-center gap-2 text-sm font-semibold text-primary">
                <Info className="h-4 w-4 text-fpl-green" />
                What are Defensive Contributions?
              </span>
              <span className="text-xs text-muted">{showDefconInfo ? "Hide" : "Show"}</span>
            </button>
            {showDefconInfo ? (
              <div className="mt-4 space-y-2 text-sm leading-6 text-secondary">
                <p>
                  FPL awards 2 points when a player reaches the Defensive Contributions threshold in a
                  gameweek: 10 combined clearances, blocks, interceptions, or tackles for defenders, and
                  12 combined defensive actions for midfielders and forwards.
                </p>
                <p>
                  The rate shown above is per 90 minutes. A strong rate can make a defensive-minded
                  budget player a useful enabler even when their attacking points or price look modest.
                </p>
              </div>
            ) : null}
          </Panel>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <PriceMoverPanel
            title="Likely to rise in price"
            icon={<TrendingUp className="h-4 w-4 text-fpl-green" />}
            rows={risers}
            tone="green"
            onSelect={openDrawer}
          />
          <PriceMoverPanel
            title="Likely to drop"
            icon={<TrendingDown className="h-4 w-4 text-fpl-red" />}
            rows={fallers}
            tone="red"
            onSelect={openDrawer}
          />
        </div>
      )}
    </div>
  );
}

function UpgradeRow({
  upgrade,
  onSelect,
}: {
  upgrade: Upgrade;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="rounded-lg border border-fpl-border bg-[#161616] p-4">
      <div className="grid grid-cols-[minmax(0,1fr)_40px_minmax(0,1fr)_auto] items-center gap-3">
        <PlayerTransferSide player={upgrade.outgoing} label="OUT" onSelect={onSelect} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-fpl-border bg-black/20">
          <ArrowRight className="h-4 w-4 text-muted" />
        </div>
        <PlayerTransferSide player={upgrade.incoming} label="IN" onSelect={onSelect} />
        <div className="text-right font-mono text-sm font-bold text-fpl-green">
          +{points(upgrade.delta)} pts
          <div className="mt-1 font-sans text-[11px] font-semibold text-fpl-green">
            better predicted score
          </div>
        </div>
      </div>
    </div>
  );
}

function PlayerTransferSide({
  player,
  label,
  onSelect,
}: {
  player: SquadPlayer | Candidate;
  label: "OUT" | "IN";
  onSelect: (name: string) => void;
}) {
  return (
    <button type="button" onClick={() => onSelect(player.name)} className="flex min-w-0 items-center gap-3 text-left">
      <img
        src={kitUrl(player.team_code, player.team, player.name)}
        alt={`${displayTeam(player.team, player.name)} kit`}
        className="h-12 w-12 shrink-0 object-contain"
      />
      <div className="min-w-0">
        <div className={`text-[10px] font-bold ${label === "OUT" ? "text-fpl-red" : "text-fpl-green"}`}>
          {label}
        </div>
        <div className="truncate text-sm font-semibold text-primary">
          {displayPlayerName(player.name, "web_name" in player ? player.web_name : undefined)}
        </div>
        <div className="truncate text-xs text-muted">
          {displayTeam(player.team, player.name)} · {price(player.price ?? null)}
        </div>
      </div>
    </button>
  );
}

function PriceMoverPanel({
  title,
  icon,
  rows,
  tone,
  onSelect,
}: {
  title: string;
  icon: ReactNode;
  rows: Candidate[];
  tone: "green" | "red";
  onSelect: (name: string) => void;
}) {
  return (
    <Panel>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-[18px] font-semibold text-primary">
            {icon}
            {title}
          </h2>
          <p className="mt-1 text-[11px] italic text-muted">
            Rule-based estimate from ownership, minutes security, and model signal.
          </p>
        </div>
      </div>
      <div className="space-y-3">
        {rows.map((player) => (
          <button
            type="button"
            key={player.name}
            onClick={() => onSelect(player.name)}
            className="grid w-full grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-fpl-border bg-[#161616] p-3 text-left hover:bg-fpl-raised"
          >
            <img
              src={kitUrl(player.team_code, player.team, player.name)}
              alt={`${displayTeam(player.team, player.name)} kit`}
              className="h-10 w-10 object-contain"
            />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-primary">
                {displayPlayerName(player.name, player.web_name)}
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-muted">
                <span>{displayTeam(player.team, player.name)}</span>
                <span>{price(player.price)}</span>
                <div className="h-1.5 w-24 rounded bg-fpl-border">
                  <div
                    className={`h-1.5 rounded ${tone === "green" ? "bg-fpl-green" : "bg-fpl-red"}`}
                    style={{ width: `${Math.min(100, player.selected_by_percent ?? 0)}%` }}
                  />
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-sm text-primary">{points(player.selected_by_percent, 0)}%</div>
              <div className={`text-[11px] ${tone === "green" ? "text-fpl-green" : "text-fpl-red"}`}>
                {tone === "green" ? "rise signal" : "drop signal"}
              </div>
            </div>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function TransferSignal({ player }: { player: Candidate }) {
  const start = player.start_likelihood ?? 0;
  const score = player.transfer_rank_score ?? 0;
  if (start < 0.4) return <SignalPill tone="amber">Minutes risk</SignalPill>;
  if (player.safety_tier === "Risky") return <SignalPill tone="amber">Risky</SignalPill>;
  if (player.safety_tier === "Safe") return <SignalPill tone="green">Safe</SignalPill>;
  if (score >= 0.45) return <SignalPill tone="green">Strong buy</SignalPill>;
  if ((player.selected_by_percent ?? 0) >= 25) return <SignalPill tone="gold">Template</SignalPill>;
  return <SignalPill tone="muted">Watch</SignalPill>;
}

function SignalPill({ tone, children }: { tone: "green" | "gold" | "amber" | "muted"; children: ReactNode }) {
  const className =
    tone === "green"
      ? "border-fpl-green/30 bg-fpl-green/10 text-fpl-green"
      : tone === "gold"
        ? "border-fpl-gold/30 bg-fpl-gold/10 text-fpl-gold"
        : tone === "amber"
          ? "border-fpl-amber/30 bg-fpl-amber/10 text-fpl-amber"
          : "border-fpl-border bg-fpl-raised text-muted";
  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${className}`}>{children}</span>;
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
        active ? "bg-fpl-green text-fpl-dark" : "text-secondary hover:text-primary"
      }`}
    >
      {children}
    </button>
  );
}

interface UpgradeGroup {
  position: PositionFilter;
  outgoing: SquadPlayer | null;
  replacements: Upgrade[];
}

interface Upgrade {
  outgoing: SquadPlayer;
  incoming: Candidate;
  delta: number;
}

function buildUpgradeGroups(squad: SquadPlayer[], candidates: Candidate[], squadKeys: Set<string>): UpgradeGroup[] {
  return positionFilters
    .filter((item): item is Exclude<PositionFilter, "All"> => item !== "All")
    .map((position) => {
      const outgoing =
        squad
          .filter((player) => positionCode(player.position) === position)
          .sort((a, b) => predicted(a) - predicted(b))[0] ?? null;
      return {
        position,
        outgoing,
        replacements: outgoing ? replacementsFor(outgoing, candidates, squadKeys) : [],
      };
    });
}

function replacementsFor(outgoing: SquadPlayer, candidates: Candidate[], squadKeys: Set<string>): Upgrade[] {
  const outgoingProjection = predicted(outgoing);
  const strict = replacementCandidates(outgoing, candidates, squadKeys, 1.5);
  const pool = strict.length ? strict : replacementCandidates(outgoing, candidates, squadKeys, 3);
  return pool
    .sort((a, b) => projected(b) - projected(a) || (b.transfer_rank_score ?? 0) - (a.transfer_rank_score ?? 0))
    .slice(0, 3)
    .map((incoming) => ({
      outgoing,
      incoming,
      delta: projected(incoming) - outgoingProjection,
    }));
}

function replacementCandidates(
  outgoing: SquadPlayer,
  candidates: Candidate[],
  squadKeys: Set<string>,
  budgetWindow: number,
): Candidate[] {
  const outgoingProjection = predicted(outgoing);
  const outgoingPrice = outgoing.price ?? 0;
  return candidates.filter((candidate) => {
    const priceGap = Math.abs(candidate.price - outgoingPrice);
    return (
      !squadKeys.has(playerKey(candidate)) &&
      positionCode(candidate.position) === positionCode(outgoing.position) &&
      projected(candidate) > outgoingProjection &&
      priceGap <= budgetWindow &&
      (candidate.start_likelihood ?? 0) >= 0.35
    );
  });
}

function buildRisers(candidates: Candidate[]): Candidate[] {
  return [...candidates]
    .filter((player) => (player.selected_by_percent ?? 0) > 0 && player.total_points > 0 && player.start_likelihood >= 0.65)
    .sort((a, b) => riseScore(b) - riseScore(a))
    .slice(0, 5);
}

function buildFallers(candidates: Candidate[], riserNames: Set<string>): Candidate[] {
  return [...candidates]
    .filter((player) => {
      if (riserNames.has(player.name)) return false;
      const ownedEnough = (player.selected_by_percent ?? 0) >= 1;
      const weakSignal = player.start_likelihood < 0.45 || player.transfer_rank_score < 0.05 || player.total_points <= 15;
      return ownedEnough && weakSignal;
    })
    .sort((a, b) => dropScore(b) - dropScore(a))
    .slice(0, 5);
}

function predicted(player: SquadPlayer): number {
  return playerXp(player);
}

function projected(player: Candidate): number {
  return player.expected_points;
}

function mergeCandidateProjections(ranked: Player[], projections: CaptainPick[]): Candidate[] {
  const byId = new Map(
    projections
      .filter((player): player is CaptainPick & { element_id: number } => typeof player.element_id === "number")
      .map((player) => [player.element_id, player]),
  );
  return ranked.flatMap((player) => {
    const projection = typeof player.element_id === "number" ? byId.get(player.element_id) : undefined;
    return projection
      ? [{
          ...player,
          raw_xp: projection.raw_xp,
          expected_points: projection.expected_points,
          start_adjusted_xp: projection.start_adjusted_xp,
          captain_expected_points: projection.captain_expected_points,
          captaincy_score: projection.captaincy_score,
          projection_contract_version: projection.projection_contract_version,
          start_likelihood: projection.start_likelihood,
        }]
      : [];
  });
}

function riseScore(player: Candidate): number {
  return (
    (player.transfer_rank_score ?? 0) * 100 +
    (player.start_likelihood ?? 0) * 16 +
    (player.ppg ?? 0) * 3 +
    Math.min(player.selected_by_percent ?? 0, 35) * 0.2
  );
}

function dropScore(player: Candidate): number {
  return (
    Math.min(player.selected_by_percent ?? 0, 35) * 1.2 +
    (1 - (player.start_likelihood ?? 0)) * 30 +
    Math.max(0, 0.08 - (player.transfer_rank_score ?? 0)) * 100
  );
}

function playerKey(player: Pick<Player, "element_id" | "name"> | Pick<SquadPlayer, "element_id" | "name">): string {
  return player.element_id ? `id:${player.element_id}` : `name:${normalized(player.name)}`;
}
