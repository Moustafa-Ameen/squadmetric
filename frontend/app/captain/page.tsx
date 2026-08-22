"use client";

import { ArrowRight, Crown, Info, Repeat2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, HeroSkeleton } from "@/components/LoadingState";
import { DecisionStatusNotice, SquadScopeNotice } from "@/components/DecisionStatusNotice";
import { Panel } from "@/components/Panel";
import { isSeasonEndedState, SeasonTransitionNotice } from "@/components/SeasonTransitionNotice";
import { SectionHeader } from "@/components/SectionHeader";
import { StartLikelihood } from "@/components/StartLikelihood";
import { useDrawer } from "@/context/DrawerContext";
import { apiErrorCode, getCaptaincyPredictions, getCurrentGameweek, getSeasonState, getSquad } from "@/lib/api";
import { squadAccessState } from "@/lib/decisionState";
import { kitUrl, normalized, points, positionCode } from "@/lib/format";
import type { CaptainPick, SeasonState, SquadPlayer } from "@/lib/types";

export default function CaptainPage() {
  const { openDrawer } = useDrawer();
  const [picks, setPicks] = useState<CaptainPick[]>([]);
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [teamConnected, setTeamConnected] = useState(false);
  const [savedTeamId, setSavedTeamId] = useState("");
  const [squadErrorCode, setSquadErrorCode] = useState<string | null>(null);
  const [showMethod, setShowMethod] = useState(false);
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
          getCaptaincyPredictions(),
          teamId
            ? getCurrentGameweek()
                .then((gw) => getSquad(teamId, gw.current_gw ?? 1))
                .catch((error: unknown) => {
                  setSquadErrorCode(apiErrorCode(error));
                  return [];
                })
            : Promise.resolve([]),
        ]);
      })
      .then((result) => {
        if (!result) return;
        const [predictionRows, squadRows] = result;
        setPicks(predictionRows);
        setSquad(squadRows);
        setTeamConnected(squadRows.length > 0);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const squadKeys = useMemo(() => new Set(squad.map(playerKey)), [squad]);
  const squadCaptainRows = useMemo(
    () =>
      squad
        .map((player) => {
          const prediction = picks.find((pick) => playerKey(pick) === playerKey(player))
            ?? picks.find((pick) => normalized(pick.name) === normalized(player.name));
          return toCaptainPick(player, prediction);
        })
        .sort((a, b) => score(b) - score(a)),
    [picks, squad],
  );
  const rankingRows = teamConnected && squadCaptainRows.length ? squadCaptainRows : picks.slice(0, 10);
  const squadState = squadAccessState(savedTeamId, squad.length, squadErrorCode, false);

  if (loading) return <HeroSkeleton />;
  if (error) return <ErrorState />;
  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Who should I captain?" subtitle="Captaincy recommendations are not decision-ready" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }
  if (seasonState && isSeasonEndedState(seasonState.season_state)) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Who should I captain?" subtitle="Captaincy projections are paused between seasons" />
        <SeasonTransitionNotice seasonState={seasonState} />
      </div>
    );
  }
  if (!picks.length) return <EmptyState />;

  const globalTop = picks[0];
  const heroPick = rankingRows[0] ?? globalTop;
  const viceCaptain = rankingRows.find((player) => player.name !== heroPick.name);
  const globalTopNotOwned = teamConnected && globalTop && !squadKeys.has(playerKey(globalTop));

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Who should I captain this week?"
        subtitle={teamConnected ? "Squad-aware captaincy using expected points and start likelihood." : "Generic captaincy ranking until your squad is available."}
      />
      <SquadScopeNotice state={squadState} />

      <button
        type="button"
        onClick={() => openDrawer(heroPick.name)}
        className="fpl-card-shadow w-full rounded-lg border border-fpl-border border-l-4 border-l-fpl-gold bg-[linear-gradient(135deg,#0d1a0d_0%,#161616_100%)] p-6 text-left shadow-[-4px_0_20px_rgba(255,215,0,0.2)]"
      >
        <div className="grid gap-5 md:grid-cols-[96px_minmax(0,1fr)_auto] md:items-center">
          <img
            src={kitUrl(heroPick.team_code)}
            alt={`${heroPick.team} kit`}
            className="h-20 w-20 object-contain"
          />
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-fpl-gold">
              {teamConnected ? "Your captain pick this week" : "Top captain pick this week"}
            </div>
            <h2 className="mt-2 truncate text-[28px] font-bold leading-tight text-primary">{heroPick.name}</h2>
            <div className="mt-1 text-sm text-secondary">
              {heroPick.team} · {positionCode(heroPick.position)}
            </div>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-secondary">
              {heroPick.reasoning ?? "Best blend of expected points and likelihood of starting."}
            </p>
            {viceCaptain ? (
              <p className="mt-3 text-[13px] text-muted">or consider {viceCaptain.name} as VC</p>
            ) : null}
          </div>
          <div className="text-left md:text-right">
            <div className="font-mono text-[48px] font-bold leading-none text-fpl-gold">
              {points(score(heroPick))}
            </div>
            <div className="mt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
              Raw xP projection
            </div>
            <div className="mt-4 inline-flex rounded-full bg-fpl-green/15 px-3 py-1">
              <StartLikelihood value={heroPick.start_likelihood} />
            </div>
          </div>
        </div>
      </button>

      {globalTopNotOwned ? (
        <div className="flex items-center gap-3 rounded-lg border border-fpl-gold/20 bg-fpl-card/80 px-4 py-3 text-sm text-secondary">
          <Repeat2 className="h-4 w-4 shrink-0 text-fpl-gold" />
          <span>
            {globalTop.name} has the highest captaincy expected points but isn&apos;t in your squad.
            Consider transferring him in.
          </span>
        </div>
      ) : null}

      {!teamConnected ? (
        <div className="rounded-lg border border-fpl-border bg-fpl-card/80 px-4 py-3 text-sm text-muted">
          Connect your team for a personalised pick.
        </div>
      ) : null}

      <Panel title="Full captain ranking">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-fpl-card text-xs uppercase text-muted">
              <tr>
                <th className="pb-3 pr-3">Rank</th>
                <th className="pb-3 pr-3">Kit</th>
                <th className="pb-3 pr-3">Player</th>
                <th className="pb-3 pr-3">Team</th>
                <th className="pb-3 pr-3 text-right">Expected Pts</th>
                <th className="pb-3 pr-3 text-right">Start %</th>
                <th className="pb-3 text-right">Raw xP</th>
              </tr>
            </thead>
            <tbody>
              {rankingRows.map((player, index) => (
                <tr
                  key={`${player.name}-${index}`}
                  className={`cursor-pointer border-b border-fpl-border transition hover:bg-fpl-green/5 ${
                    index === 0
                      ? "border-l-4 border-l-fpl-gold bg-fpl-gold/[0.04]"
                      : index % 2 === 0
                        ? "bg-[#161616]"
                        : "bg-[#181818]"
                  }`}
                  onClick={() => openDrawer(player.name)}
                >
                  <td className="py-3 pr-3 pl-3 font-mono text-muted">
                    {index === 0 ? <Crown className="h-4 w-4 text-fpl-gold" /> : index + 1}
                  </td>
                  <td className="py-3 pr-3">
                    <img
                      src={kitUrl(player.team_code)}
                      alt={`${player.team} kit`}
                      className="h-10 w-10 object-contain"
                    />
                  </td>
                  <td className="py-3 pr-3 font-semibold text-primary">{player.name}</td>
                  <td className="py-3 pr-3 text-muted">{player.team}</td>
                  <td className="py-3 pr-3 text-right font-mono text-primary">{points(player.expected_points)}</td>
                  <td className="py-3 pr-3 text-right">
                    <StartLikelihood value={player.start_likelihood} />
                  </td>
                  <td className="py-3 text-right font-mono font-bold text-fpl-green">{points(score(player))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel>
        <div className="mb-4 rounded-lg border border-fpl-gold/25 bg-fpl-gold/[0.04] p-4 text-sm leading-6 text-secondary">
          <span className="font-semibold text-fpl-gold">Captaincy model:</span> captain picks use
          our Ridge Regression model rather than the lower-MAE Gradient Boosting model. Backtesting
          showed Ridge is better at identifying explosive high-ceiling performances, which matters
          more for captaincy than minimizing average prediction error.
        </div>
        <button
          type="button"
          onClick={() => setShowMethod((value) => !value)}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <span className="flex items-center gap-2 text-sm font-semibold text-primary">
            <Info className="h-4 w-4 text-fpl-gold" />
            How are captain expected points calculated?
          </span>
          <span className="text-xs text-muted">{showMethod ? "Hide" : "Show"}</span>
        </button>

        {showMethod ? (
          <div className="mt-5">
            <div className="grid gap-3 md:grid-cols-[1fr_32px_1fr_32px_1fr] md:items-center">
              <MethodStep label="Raw xP" value={`${points(heroPick.raw_xp)} pts`} />
              <ArrowRight className="mx-auto hidden h-5 w-5 text-muted md:block" />
              <MethodStep label="Start likelihood" value={`${Math.round(heroPick.start_likelihood * 100)}%`} />
              <ArrowRight className="mx-auto hidden h-5 w-5 text-muted md:block" />
              <MethodStep label="Expected points" value={points(heroPick.expected_points)} accent />
            </div>
            <p className="mt-4 text-sm leading-6 text-secondary">
              Captain scores double points. Triple Captain scores triple, so use your TC chip on a
              double gameweek player when the fixture quality and minutes outlook are strong.
            </p>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function toCaptainPick(player: SquadPlayer, prediction?: CaptainPick): CaptainPick {
  return {
    name: player.name,
    element_id: player.element_id,
    team: prediction?.team ?? player.team,
    position: prediction?.position ?? player.position,
    price: prediction?.price ?? player.price ?? undefined,
    start_likelihood: prediction?.start_likelihood ?? player.start_likelihood ?? 0,
    raw_xp: prediction?.raw_xp ?? player.raw_xp ?? 0,
    expected_points: prediction?.expected_points ?? player.expected_points ?? 0,
    start_adjusted_xp: prediction?.start_adjusted_xp ?? player.expected_points ?? 0,
    captain_expected_points: prediction?.captain_expected_points ?? 2 * (player.expected_points ?? 0),
    captaincy_score: prediction?.captaincy_score ?? player.expected_points ?? 0,
    projection_contract_version: prediction?.projection_contract_version ?? "w2-v1",
    team_code: prediction?.team_code ?? player.team_code,
    web_name: prediction?.web_name ?? player.web_name,
    reasoning: prediction?.reasoning ?? "Best captain option from your connected squad.",
  };
}

function score(player: CaptainPick): number {
  return player.expected_points ?? 0;
}

function MethodStep({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-fpl-border bg-fpl-raised p-4 text-center">
      <div className="text-[11px] uppercase tracking-[0.12em] text-muted">{label}</div>
      <div className={`mt-2 font-mono text-xl font-bold ${accent ? "text-fpl-green" : "text-primary"}`}>
        {value}
      </div>
    </div>
  );
}

function playerKey(player: Pick<CaptainPick, "element_id" | "name"> | Pick<SquadPlayer, "element_id" | "name">): string {
  return player.element_id ? `id:${player.element_id}` : `name:${normalized(player.name)}`;
}
