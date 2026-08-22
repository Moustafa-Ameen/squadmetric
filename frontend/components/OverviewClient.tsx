"use client";

import Link from "next/link";
import { ArrowRight, Crown, ShieldCheck, Sparkles, Target, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { FixtureChip } from "@/components/FixtureChip";
import { SquadScopeNotice } from "@/components/DecisionStatusNotice";
import { EmptyState } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { isSeasonEndedState, SeasonTransitionNotice } from "@/components/SeasonTransitionNotice";
import { StartLikelihood } from "@/components/StartLikelihood";
import { StatCard } from "@/components/StatCard";
import { useDrawer } from "@/context/DrawerContext";
import { apiErrorCode, getCurrentGameweek, getSquad } from "@/lib/api";
import { squadAccessMessage, squadAccessState } from "@/lib/decisionState";
import { fixtureTickerRows, visibleFixtures } from "@/lib/fixtures";
import { displayPlayerName, displayTeam, kitUrl, normalized, points, positionCode } from "@/lib/format";
import { selectCurrentSquadMetrics } from "@/lib/squadMetrics";
import type {
  AccuracyResult,
  CaptainPick,
  FixtureTick,
  Player,
  SeasonState,
  SquadPlayer,
  TransferTarget,
} from "@/lib/types";

type ProjectionPlayer = Pick<
  CaptainPick,
  | "name"
  | "element_id"
  | "team"
  | "position"
  | "team_code"
  | "web_name"
  | "start_likelihood"
  | "raw_xp"
  | "expected_points"
  | "captain_expected_points"
  | "captaincy_score"
>;

interface OverviewClientProps {
  playerCount: number;
  captains: CaptainPick[];
  predictions: CaptainPick[];
  transfers: TransferTarget[];
  fixtures: FixtureTick[];
  gems: Player[];
  accuracy: AccuracyResult[];
  seasonState: SeasonState;
}

export function OverviewClient({
  playerCount,
  captains,
  predictions,
  transfers,
  fixtures,
  gems,
  accuracy,
  seasonState,
}: OverviewClientProps) {
  const { openDrawer } = useDrawer();
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [savedTeamId, setSavedTeamId] = useState("");
  const [squadErrorCode, setSquadErrorCode] = useState<string | null>(null);
  const [squadLoading, setSquadLoading] = useState(false);

  useEffect(() => {
    const teamId = window.localStorage.getItem("fpl_team_id");
    queueMicrotask(() => setSavedTeamId(teamId ?? ""));
    if (!teamId) return;

    queueMicrotask(() => setSquadLoading(true));

    getCurrentGameweek()
      .then((gw) => getSquad(teamId, gw.current_gw ?? 1))
      .then((rows) => {
        setSquad(rows);
        setSquadErrorCode(null);
      })
      .catch((error: unknown) => {
        setSquad([]);
        setSquadErrorCode(apiErrorCode(error));
      })
      .finally(() => setSquadLoading(false));
  }, []);

  const squadMetrics = useMemo(() => selectCurrentSquadMetrics(squad), [squad]);
  const squadState = squadAccessState(savedTeamId, squad.length, squadErrorCode, squadLoading);
  const personalized = squadState === "personalized";
  const projectionPlayers = useMemo<ProjectionPlayer[]>(() => {
    if (squadMetrics.starters.length) {
      return squadMetrics.starters.map((player) => ({
        name: player.name,
        element_id: player.element_id,
        team: player.team,
        position: player.position,
        team_code: player.team_code,
        web_name: player.web_name,
        start_likelihood: player.start_likelihood ?? 0,
        raw_xp: player.raw_xp ?? 0,
        expected_points: player.expected_points ?? 0,
        captain_expected_points: 2 * (player.expected_points ?? 0),
        captaincy_score: player.expected_points ?? 0,
      }));
    }
    return predictions.slice(0, 11);
  }, [predictions, squadMetrics.starters]);

  const predictedGwPoints = squadMetrics.starters.length
    ? squadMetrics.totalStartingXp
    : projectionPlayers.reduce((sum, player) => sum + player.expected_points, 0);
  const captainEdgeName = squadMetrics.captainPick?.web_name ?? squadMetrics.captainPick?.name ?? captains[0]?.name ?? "-";
  const viceCaptainEdgeName = squadMetrics.viceCaptainPick?.web_name ?? squadMetrics.viceCaptainPick?.name ?? "VC";
  const captaincyEdge = squadMetrics.captainPick ? squadMetrics.captaincyEdge : (captains[0]?.expected_points ?? 0);
  const topCaptain = captains[0];
  const bestAccuracy = accuracy.find((row) => row.model === "FPL Intelligence (best)") ?? accuracy[0];
  const suggestions = buildSuggestions(squad, transfers);
  const fixtureRows = fixtureTickerRows(fixtures);
  const fixtureMeta = fixtureRows[0];

  if (!playerCount) return <EmptyState />;
  if (isSeasonEndedState(seasonState.season_state)) {
    return (
      <div className="space-y-5">
        <SeasonTransitionNotice seasonState={seasonState} />
        <div className="rounded-lg border border-fpl-border bg-fpl-card p-5 text-sm text-secondary">
          The decision dashboard will return when the new season has live gameweek data. Historical model results remain available on{" "}
          <Link href="/proof" className="font-semibold text-fpl-green hover:text-primary">Proof It Works</Link>.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="fpl-card-shadow rounded-lg border border-fpl-border bg-[linear-gradient(135deg,rgba(0,255,135,0.1),rgba(16,21,20,0.96)_38%,rgba(143,76,248,0.12))] p-5">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-fpl-green">
            <Sparkles className="h-4 w-4" />
            FPL Intelligence
          </div>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-[26px] font-semibold leading-tight text-primary md:text-[32px]">
                Gameweek decision cockpit
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">
                Captain edge, transfer delta, fixture difficulty, and model proof in one scanning view.
              </p>
            </div>
            <div className="rounded-lg border border-fpl-border bg-black/20 px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.14em] text-muted">Model status</div>
              <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-primary">
                <span className="h-2 w-2 rounded-full bg-fpl-green shadow-[0_0_12px_rgba(0,255,135,0.75)]" />
                Model active · FPL {seasonState.fpl_api_season}
              </div>
            </div>
          </div>
        </div>

        <div className="fpl-card-shadow rounded-lg border border-fpl-border bg-fpl-card/95 p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">Squad link</div>
              <div className="mt-2 text-lg font-semibold text-primary">
                {personalized ? "Personalized" : savedTeamId ? "Team ID saved" : "Team ID needed"}
              </div>
            </div>
            <ShieldCheck className={`h-8 w-8 ${personalized ? "text-fpl-green" : "text-muted"}`} />
          </div>
          <p className="mt-4 text-sm leading-6 text-secondary">
            {squadAccessMessage(squadState)}
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Expected GW Points"
          value={points(predictedGwPoints)}
          subLabel={personalized ? "Your starting XI projection" : "Generic top 11 adjusted picks"}
        />
        <StatCard
          label="Captaincy Edge"
          value={`${points(captaincyEdge)} xP`}
          subLabel={`${displayPlayerName(captainEdgeName)} over ${displayPlayerName(viceCaptainEdgeName)}`}
        />
        <StatCard
          label="Model MAE"
          value={points(bestAccuracy?.adjusted_MAE ?? bestAccuracy?.raw_MAE)}
          subLabel="Lower is better"
        />
        <StatCard label="Players Tracked" value={playerCount} subLabel="Current player pool" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.9fr)]">
        <div className="space-y-6">
          <Panel title={personalized ? "Your squad projection" : "Generic top projected XI · this gameweek"}>
            <p className="mb-3 text-[13px] leading-5 text-secondary">
              {personalized
                ? "This is your current FPL starting XI with this gameweek's model projection beside each player."
                : "This is a generic highest-projected XI, not a recommendation for your saved team."}
            </p>
            <div className="mb-3"><SquadScopeNotice state={squadState} /></div>
            <ProjectionPitch players={projectionPlayers} onSelect={openDrawer} />
          </Panel>

          <Panel title="Suggested Moves">
            {!personalized ? (
              <p className="mb-4 text-sm italic text-muted">
                Generic targets only—no outgoing player below comes from your squad.
              </p>
            ) : null}
            <div className="space-y-4">
              {suggestions.slice(0, 2).map(({ incoming, outgoing, gain }) => (
                <div
                  key={`${incoming.name}-${outgoing?.name}`}
                  className="fpl-suggested-move rounded-lg border border-fpl-border bg-fpl-raised/50 p-4"
                >
                  <div className="grid grid-cols-[minmax(0,1fr)_44px_minmax(0,1fr)] items-center gap-3">
                    <button
                      type="button"
                      onClick={() => outgoing && openDrawer(outgoing.name)}
                      className="flex min-w-0 items-center gap-3 text-left"
                    >
                      <img
                        src={kitUrl(outgoing?.team_code, outgoing?.team, outgoing?.name)}
                        alt={`${displayTeam(outgoing?.team, outgoing?.name) || "Outgoing"} kit`}
                        className="h-12 w-12 shrink-0 object-contain"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="shrink-0 rounded bg-fpl-red/15 px-2 py-1 text-[11px] font-bold text-fpl-red">
                            OUT
                          </span>
                          <span className="truncate text-sm font-bold text-primary">
                            {outgoing?.name ?? "Bench option"}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-xs text-muted">
                          {displayTeam(outgoing?.team, outgoing?.name) || "Unknown"} - low xP
                        </div>
                      </div>
                    </button>
                    <div className="move-arrow flex h-10 w-10 items-center justify-center rounded-full border border-fpl-border bg-black/20 text-muted">
                      <ArrowRight className="h-[18px] w-[18px] text-fpl-green" />
                    </div>
                    <button
                      type="button"
                      onClick={() => openDrawer(incoming.name)}
                      className="flex min-w-0 items-center gap-3 text-left"
                    >
                      <img
                        src={kitUrl(incoming.team_code, incoming.team, incoming.name)}
                        alt={`${displayTeam(incoming.team, incoming.name)} kit`}
                        className="h-12 w-12 shrink-0 object-contain"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="shrink-0 rounded bg-fpl-green/15 px-2 py-1 text-[11px] font-bold text-fpl-green">
                            IN
                          </span>
                          <span className="truncate text-sm font-bold text-primary">{incoming.name}</span>
                        </div>
                        <div className="mt-1 truncate text-xs text-muted">
                          {displayTeam(incoming.team, incoming.name)} - {positionCode(incoming.position)} - {"\u00a3"}{points(incoming.price)}m
                        </div>
                      </div>
                    </button>
                  </div>
                  <div className="mt-3 border-t border-white/[0.06] pt-2 pl-1 text-[13px] font-semibold text-fpl-green">
                    {outgoing ? `+${points(Math.max(gain, 0))} expected-points gain` : `${points(gain)} expected points`}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Captaincy Edge">
            {squadMetrics.captainPick || topCaptain ? (
              <button
                type="button"
                onClick={() => openDrawer(squadMetrics.captainPick?.name ?? topCaptain.name)}
                className="w-full rounded-lg border border-fpl-gold/25 bg-[linear-gradient(135deg,rgba(255,200,87,0.13),rgba(255,255,255,0.025))] p-4 text-left hover:border-fpl-gold/50"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-fpl-gold">
                      <Crown className="h-4 w-4" />
                      Captaincy Edge
                    </div>
                    <div className="mt-3 truncate text-xl font-semibold text-primary">
                      {displayPlayerName(squadMetrics.captainPick?.name ?? topCaptain.name, squadMetrics.captainPick?.web_name)}
                    </div>
                    <div className="mt-1 text-sm text-secondary">
                      {displayTeam(squadMetrics.captainPick?.team ?? topCaptain.team, squadMetrics.captainPick?.name ?? topCaptain.name)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-2xl font-bold text-fpl-gold">
                      +{points(captaincyEdge)} xP
                    </div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.1em] text-muted">
                      over vice-captain
                    </div>
                    <div className="mt-2 flex justify-end">
                      <StartLikelihood value={squadMetrics.captainPick?.start_likelihood ?? topCaptain.start_likelihood} />
                    </div>
                  </div>
                </div>
                <p className="mt-4 text-sm leading-6 text-secondary">
                  {squadMetrics.captainPick && squadMetrics.viceCaptainPick
                    ? `${displayPlayerName(squadMetrics.captainPick.name, squadMetrics.captainPick.web_name)} projects ${points(squadMetrics.captaincyEdge)} xP ahead of ${displayPlayerName(squadMetrics.viceCaptainPick.name, squadMetrics.viceCaptainPick.web_name)}.`
                    : topCaptain.reasoning ?? "Best blend of projected points and start confidence."}
                </p>
              </button>
            ) : null}
          </Panel>

          <Panel title="Fixture Ticker">
            <div className="mb-3 flex flex-wrap gap-2 text-[11px] font-semibold text-muted">
              <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1">
                {fixtureMeta?.source ?? seasonState.fixture_source}
              </span>
              <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1">
                {fixtureMeta?.season ?? seasonState.fixture_season}
              </span>
              <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1 text-fpl-amber">
                {fixtureMeta?.difficulty_source ?? seasonState.difficulty_source}
              </span>
            </div>
            <div className="space-y-2">
              {fixtureRows.slice(0, 8).map((team) => (
                <div key={team.team} className="grid grid-cols-[1fr_auto] items-center gap-4">
                  <div className="truncate text-sm text-primary">{team.team}</div>
                  <div className="flex gap-2">
                    {visibleFixtures(team).map((fixture, index) => (
                      <FixtureChip
                        key={`${team.team}-${fixture.gw}-${index}`}
                        difficulty={fixture.difficulty}
                        opponentShortName={fixture.opponent}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Differential Radar">
            <div className="space-y-3">
              {gems.slice(0, 3).map((player) => (
                <button
                  type="button"
                  key={player.name}
                  onClick={() => openDrawer(player.name)}
                  className="w-full rounded-lg border border-fpl-border bg-fpl-raised/45 p-3 text-left hover:bg-fpl-raised"
                >
                  <div className="font-semibold text-primary">{player.name}</div>
                  <div className="mt-1 text-xs text-secondary">
                    {player.team} - {points(player.selected_by_percent, 0)}% owned
                  </div>
                  <div className="mt-3 h-1 rounded bg-fpl-border">
                    <div
                      className="h-1 rounded bg-fpl-green"
                      style={{ width: `${Math.min(player.selected_by_percent ?? 0, 100)}%` }}
                    />
                  </div>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Model Proof">
            <div className="grid grid-cols-2 gap-3">
              <ProofMetric
                icon={<Target className="h-4 w-4" />}
                label="Best MAE"
                value={points(bestAccuracy?.adjusted_MAE ?? bestAccuracy?.raw_MAE)}
              />
              <ProofMetric
                icon={<TrendingUp className="h-4 w-4" />}
                label="Pool"
                value={playerCount.toLocaleString()}
              />
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function buildSuggestions(
  squad: SquadPlayer[],
  transfers: TransferTarget[],
): { outgoing?: SquadPlayer | Player; incoming: TransferTarget; gain: number }[] {
  if (!squad.length) {
    return transfers.slice(0, 2).map((incoming) => ({
      incoming,
      outgoing: undefined,
      gain: incoming.expected_points,
    }));
  }

  const squadKeys = new Set(squad.map(playerKey));
  const candidates = squad
    .filter((player) => !player.is_captain)
    .sort((a, b) => (a.expected_points ?? 0) - (b.expected_points ?? 0))
    .slice(0, 2);
  return candidates.flatMap((outgoing) => {
    const outgoingPosition = positionCode(outgoing.position);
    const outgoingPrice = outgoing.price;
    const outgoingProjected = outgoing.expected_points ?? 0;
    const incoming = transfers
      .filter((player) => {
        const incomingProjected = player.expected_points;
        const priceGap = typeof outgoingPrice === "number" ? Math.abs(player.price - outgoingPrice) : 0;
        return (
          !squadKeys.has(playerKey(player)) &&
          positionCode(player.position) === outgoingPosition &&
          incomingProjected > outgoingProjected &&
          priceGap <= 1
        );
      })
      .sort((a, b) => b.transfer_rank_score - a.transfer_rank_score)[0];
    return incoming
      ? [
          {
            outgoing,
            incoming,
            gain: incoming.expected_points - (outgoing.expected_points ?? 0),
          },
        ]
      : [];
  });
}

function ProjectionPitch({ players, onSelect }: { players: ProjectionPlayer[]; onSelect: (name: string) => void }) {
  const rows = projectionRows(players);
  return (
    <div className="relative h-[clamp(360px,calc(100vh-420px),500px)] max-h-[500px] overflow-hidden rounded-lg border border-fpl-border bg-[linear-gradient(180deg,#0b6a39_0%,#07502d_48%,#064325_100%)] p-3">
      <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-white/12" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/12" />
      <div className="pointer-events-none absolute inset-3 rounded border border-white/10" />
      <div className="relative grid h-full content-between gap-2">
        {rows.map((row, index) => (
          <div key={index} className="flex flex-wrap justify-center gap-x-3 gap-y-1 md:gap-x-4">
            {row.map((player) => (
              <ProjectionCard key={`${player.name}-${index}`} player={player} onSelect={onSelect} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function ProjectionCard({ player, onSelect }: { player: ProjectionPlayer; onSelect: (name: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(player.name)}
      className="fpl-pitch-card w-[104px] rounded-lg bg-black/25 p-2 text-center backdrop-blur hover:bg-black/35"
      aria-label={player.name}
    >
      <img
        src={kitUrl(player.team_code, player.team, player.name)}
        alt={`${displayTeam(player.team, player.name)} kit`}
        className="mx-auto h-[54px] w-[66px] object-contain"
      />
      <div className="mt-1 truncate text-[12px] font-semibold text-white">
        {displayPlayerName(player.name, player.web_name)}
      </div>
      <div className="font-mono text-xs font-bold text-fpl-green">
        {points(player.expected_points)} xP
      </div>
    </button>
  );
}

function projectionRows(players: ProjectionPlayer[]) {
  const rowDefinitions = [
    { code: "GK", take: 1 },
    { code: "DEF", take: 5 },
    { code: "MID", take: 5 },
    { code: "FWD", take: 3 },
  ];
  const used = new Set<string>();
  const rows = rowDefinitions
    .map(({ code, take }) => {
      const row = players.filter((player) => positionCode(player.position) === code && !used.has(player.name)).slice(0, take);
      row.forEach((player) => used.add(player.name));
      return row;
    })
    .filter((row) => row.length);
  const remaining = players.filter((player) => !used.has(player.name));
  if (remaining.length) rows.push(remaining);
  return rows.length ? rows : [players];
}

function playerKey(player: Pick<Player, "element_id" | "name"> | Pick<SquadPlayer, "element_id" | "name"> | Pick<TransferTarget, "element_id" | "name">): string {
  return player.element_id ? `id:${player.element_id}` : `name:${normalized(player.name)}`;
}

function ProofMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-fpl-border bg-fpl-raised p-3">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-muted">
        <span className="text-fpl-green">{icon}</span>
        {label}
      </div>
      <div className="mt-3 font-mono text-lg font-bold text-primary">{value}</div>
    </div>
  );
}
