"use client";

import Link from "next/link";
import { ArrowRight, Banknote, RefreshCw, Trophy, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { EmptyState, ErrorState, PitchSkeleton } from "@/components/LoadingState";
import { SectionHeader } from "@/components/SectionHeader";
import { SquadPitch, type VisualSquadPlayer } from "@/components/SquadPitch";
import { isSeasonEndedState, SeasonTransitionNotice } from "@/components/SeasonTransitionNotice";
import { apiErrorCode, getCurrentGameweek, getSeasonState, getSquad, getTeam } from "@/lib/api";
import { points, price } from "@/lib/format";
import { selectCurrentSquadMetrics } from "@/lib/squadMetrics";
import type { SeasonState, SquadPlayer, TeamData } from "@/lib/types";

export default function SquadPage() {
  const [teamId, setTeamId] = useState("");
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [team, setTeam] = useState<TeamData | null>(null);
  const [showBench, setShowBench] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);

  useEffect(() => {
    const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    queueMicrotask(() => {
      setTeamId(savedTeamId);
      setShowBench(window.localStorage.getItem("show_bench_players") !== "false");
    });
    if (!savedTeamId) {
      queueMicrotask(() => setLoading(false));
      return;
    }

    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        if (isSeasonEndedState(state.season_state) || !state.recommendations_ready) return null;
        return getCurrentGameweek().then((gw) => Promise.all([
          getSquad(savedTeamId, gw.current_gw ?? 1),
          getTeam(savedTeamId),
        ]));
      })
      .then((result) => {
        if (!result) return;
        setSquad(result[0]);
        setTeam(result[1]);
      })
      .catch((caught: unknown) => {
        setErrorCode(apiErrorCode(caught));
        setError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const metrics = useMemo(() => selectCurrentSquadMetrics(squad), [squad]);
  const visualPlayers = useMemo<VisualSquadPlayer[]>(() => [
    ...metrics.starters.map((player, index) => toVisualPlayer(player, true, index)),
    ...metrics.bench.map((player, index) => toVisualPlayer(player, false, index)),
  ], [metrics]);

  if (loading) return <PitchSkeleton />;
  if (!teamId) return <ConnectTeamState />;
  if (seasonState && !seasonState.recommendations_ready) return <div className="space-y-5"><SectionHeader title="My Team" subtitle={`FPL Team ${teamId}`} /><DecisionStatusNotice seasonState={seasonState} /></div>;
  if (errorCode === "squad_unavailable") return <div className="space-y-5"><SectionHeader title="My Team" subtitle={`FPL Team ${teamId}`} /><div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">FPL has not published this team&apos;s current picks yet. Your link is saved correctly; try again after the next deadline.</div></div>;
  if (error) return <ErrorState />;
  if (seasonState && isSeasonEndedState(seasonState.season_state)) return <div className="space-y-5"><SectionHeader title="My Team" subtitle={`FPL Team ${teamId}`} /><SeasonTransitionNotice seasonState={seasonState} /></div>;
  if (!squad.length) return <EmptyState />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionHeader title="My Team" subtitle={`${team?.team_name ?? `FPL Team ${teamId}`} · Your current squad and recommended lineup`} />
        <Link href="/onboarding" className="sm-secondary-button mb-6 px-4 py-2.5"><RefreshCw className="h-4 w-4" />Change linked team</Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <TeamMetric icon={UsersRound} label="Starting XI projection" value={`${points(metrics.totalStartingXp)} pts`} />
        <TeamMetric icon={Banknote} label="Squad value" value={price(team?.squad_value)} />
        <TeamMetric icon={Banknote} label="In the bank" value={price(team?.bank_value)} />
        <TeamMetric icon={Trophy} label="Overall rank" value={team?.overall_rank?.toLocaleString() ?? "Not ranked yet"} />
      </div>
      <SquadPitch players={visualPlayers} title="Your current lineup" showBench={showBench} />
      {!showBench ? <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-600">Bench display is hidden in your preferences. Autosub cover is still included in the recommendation engine.</div> : null}
    </div>
  );
}

function ConnectTeamState() {
  return <div className="flex min-h-[60vh] items-center justify-center"><div className="max-w-lg rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-[0_18px_55px_rgba(15,23,42,0.08)]"><div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-50 text-violet-700"><UsersRound className="h-7 w-7" /></div><h1 className="mt-5 text-2xl font-black text-slate-950">Connect your FPL team</h1><p className="mt-3 text-sm leading-6 text-slate-600">Link your public FPL Team ID once, then SquadMetric can show your real squad, bench and weekly recommendations.</p><Link href="/onboarding" className="sm-primary-button mt-6 justify-center px-5 py-3">Connect team<ArrowRight className="h-4 w-4" /></Link></div></div>;
}

function TeamMetric({ icon: Icon, label, value }: { icon: typeof UsersRound; label: string; value: string }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.05)]"><div className="flex items-center gap-2 text-xs font-bold text-slate-500"><Icon className="h-4 w-4 text-violet-600" />{label}</div><div className="mt-2 text-xl font-black tracking-tight text-slate-950">{value}</div></div>;
}

function toVisualPlayer(player: SquadPlayer, starter: boolean, benchOrder: number): VisualSquadPlayer {
  return { id: player.element_id ?? player.name, name: player.name, shortName: player.web_name, team: player.team, teamCode: player.team_code, position: player.position, expectedPoints: player.expected_points, startLikelihood: player.start_likelihood, playerPrice: player.current_price ?? player.price, starter, benchOrder, captain: player.is_captain, viceCaptain: player.is_vice_captain };
}
