"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { FixtureChip } from "@/components/FixtureChip";
import { ErrorState, TableSkeleton } from "@/components/LoadingState";
import { SquadScopeNotice } from "@/components/DecisionStatusNotice";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { useDrawer } from "@/context/DrawerContext";
import { apiErrorCode, getCurrentGameweek, getFixtureTicker, getSquad } from "@/lib/api";
import { squadAccessState } from "@/lib/decisionState";
import { fixtureTickerRows, visibleFixtures } from "@/lib/fixtures";
import type { FixtureTick, SquadPlayer } from "@/lib/types";

type FixtureRange = 3 | 5 | 8;
type FixtureView = "squad" | "targets";

const fixtureRanges: FixtureRange[] = [3, 5, 8];

export default function FixturesPage() {
  const { openDrawer } = useDrawer();
  const [fixtures, setFixtures] = useState<FixtureTick[]>([]);
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [teamId, setTeamId] = useState("");
  const [squadErrorCode, setSquadErrorCode] = useState<string | null>(null);
  const [range, setRange] = useState<FixtureRange>(5);
  const [view, setView] = useState<FixtureView>("squad");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const savedTeamId = window.localStorage.getItem("fpl_team_id") ?? "";
    queueMicrotask(() => {
      if (!cancelled) setTeamId(savedTeamId);
    });

    Promise.all([
      getFixtureTicker(),
      savedTeamId
        ? getCurrentGameweek()
            .then((gw) => getSquad(savedTeamId, gw.current_gw ?? 1))
            .catch((caught: unknown) => {
              setSquadErrorCode(apiErrorCode(caught));
              return [];
            })
        : Promise.resolve([]),
    ])
      .then(([fixtureRows, squadRows]) => {
        if (cancelled) return;
        setFixtures(fixtureRows);
        setSquad(squadRows);
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
  }, []);

  const fixtureRows = useMemo(() => fixtureTickerRows(fixtures), [fixtures]);
  const squadState = squadAccessState(teamId, squad.length, squadErrorCode, false);
  const fixtureMeta = fixtureRows[0];
  const squadFixtureRows = useMemo(
    () =>
      squad
        .slice(0, 11)
        .map((player) => {
          const team = findTeamFixtureRow(fixtureRows, player);
          const upcoming = visibleFixtures(team, 5);
          const average = averageDifficulty(upcoming);
          return { player, fixtures: upcoming, average };
        })
        .sort((a, b) => (a.average ?? 99) - (b.average ?? 99)),
    [fixtureRows, squad],
  );
  const targetTeams = useMemo(
    () =>
      fixtureRows
        .map((team) => {
          const upcoming = visibleFixtures(team, range);
          const average = averageDifficulty(upcoming);
          return { team, fixtures: upcoming, average };
        })
        .sort((a, b) => (a.average ?? 99) - (b.average ?? 99)),
    [fixtureRows, range],
  );

  if (loading) return <TableSkeleton />;
  if (error) return <ErrorState />;

  return (
    <div>
      <SectionHeader
        title="Fixtures"
        subtitle="Fixture difficulty for your squad and transfer targets"
      />

      <div className="space-y-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2 text-[11px] font-semibold text-muted">
            <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1">
              {fixtureMeta?.source ?? "Fixture source pending"}
            </span>
            <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1">
              {fixtureMeta?.season ?? "Season pending"}
            </span>
            <span className="rounded-full border border-fpl-border bg-fpl-raised px-2 py-1 text-[#92400e]">
              {fixtureMeta?.difficulty_source ?? "Difficulty source pending"}
            </span>
          </div>

          <div
            role="group"
            aria-label="Fixture view"
            className="grid w-full grid-cols-2 rounded-xl border border-fpl-border bg-fpl-raised p-1 sm:w-auto"
          >
            <button
              type="button"
              aria-pressed={view === "squad"}
              onClick={() => setView("squad")}
              className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                view === "squad"
                  ? "bg-fpl-purple text-white shadow-sm"
                  : "text-secondary hover:bg-fpl-panel hover:text-primary"
              }`}
            >
              My squad
            </button>
            <button
              type="button"
              aria-pressed={view === "targets"}
              onClick={() => setView("targets")}
              className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                view === "targets"
                  ? "bg-fpl-purple text-white shadow-sm"
                  : "text-secondary hover:bg-fpl-panel hover:text-primary"
              }`}
            >
              Team targets
            </button>
          </div>
        </div>

        {view === "squad" ? <Panel>
          <div className="mb-4">
            <h2 className="text-[18px] font-semibold text-primary">Your squad&apos;s upcoming fixtures</h2>
            <p className="mt-1 text-[13px] text-secondary">Tap a player to see more</p>
          </div>

          {squad.length ? (
            <div className="space-y-2">
              {squadFixtureRows.map(({ player, fixtures: upcoming, average }) => (
                <button
                  type="button"
                  key={player.name}
                  onClick={() => openDrawer(player.name)}
                  className="grid w-full grid-cols-[40px_minmax(0,1fr)] items-center gap-3 rounded-[10px] border border-fpl-border/70 px-3 py-3 text-left transition hover:border-fpl-green/40 hover:bg-fpl-raised sm:grid-cols-[40px_minmax(0,1fr)_auto]"
                >
                  <img
                    src={`https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${player.team_code ?? 1}-66.png`}
                    alt={`${player.team} kit`}
                    className="h-8 w-8 object-contain"
                  />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-primary">{player.name}</div>
                    <div className="truncate text-xs text-muted">{player.team}</div>
                  </div>
                <div className="col-span-2 flex min-w-0 flex-col items-start gap-1 sm:col-span-1 sm:items-end">
                  <div className="flex max-w-full gap-1.5 overflow-x-auto pb-1 sm:overflow-visible sm:pb-0">
                      {upcoming.map((fixture, index) => (
                        <FixtureChip
                          key={`${player.name}-${fixture.gw}-${index}`}
                          difficulty={fixture.difficulty}
                          opponentShortName={fixture.opponent}
                        />
                    ))}
                  </div>
                  <div className={`text-[11px] ${scoreClass(average)}`}>
                    {average === null ? "No 2026-27 fixture row" : `Avg difficulty: ${average.toFixed(1)}`}
                  </div>
                </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <SquadScopeNotice state={squadState} />
              {!teamId ? (
                <Link href="/settings" className="inline-flex text-sm font-semibold text-fpl-green hover:text-primary">
                  Open Settings
                </Link>
              ) : null}
            </div>
          )}
        </Panel> : null}

        {view === "targets" ? <Panel>
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-[18px] font-semibold text-primary">Best teams to target</h2>
              <p className="mt-1 text-[13px] text-secondary">
                Teams with the easiest fixtures over the next {range} gameweeks
              </p>
            </div>
            <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
              {fixtureRanges.map((option) => (
                <button
                  type="button"
                  key={option}
                  onClick={() => setRange(option)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                    range === option ? "bg-fpl-green text-fpl-dark" : "text-secondary hover:text-primary"
                  }`}
                >
                  Next {option} GWs
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            {targetTeams.map(({ team, fixtures: upcoming, average }) => (
              <div
                key={team.team}
                className="grid grid-cols-[minmax(0,1fr)_48px] items-center gap-x-3 gap-y-2 rounded-[10px] border border-fpl-border/70 px-3 py-3 sm:grid-cols-[minmax(120px,1fr)_auto_48px]"
              >
                <div className={`truncate text-sm font-semibold ${
                  average !== null && average <= 2.5 ? "text-fpl-green" : "text-primary"
                }`}>
                  {team.team}
                </div>
                <div className="col-span-2 flex max-w-full min-w-0 gap-1.5 overflow-x-auto pb-1 sm:col-span-1 sm:overflow-visible sm:pb-0">
                  {upcoming.map((fixture, index) => (
                    <FixtureChip
                      key={`${team.team}-${fixture.gw}-${index}`}
                      difficulty={fixture.difficulty}
                      opponentShortName={fixture.opponent}
                    />
                  ))}
                </div>
                <div className={`col-start-2 row-start-1 text-right font-mono text-sm font-semibold sm:col-start-3 ${scoreClass(average)}`}>
                  {average === null ? "-" : average.toFixed(1)}
                </div>
              </div>
            ))}
          </div>
        </Panel> : null}
      </div>
    </div>
  );
}

function findTeamFixtureRow(fixtureRows: FixtureTick[], player: SquadPlayer): FixtureTick {
  return (
    fixtureRows.find((team) => team.team_short === player.team || team.team === player.team) ?? {
      team: player.team,
      team_short: player.team,
      fixtures: [],
    }
  );
}

function averageDifficulty(fixtures: { difficulty: number }[]): number | null {
  if (!fixtures.length) return null;
  return fixtures.reduce((sum, fixture) => sum + fixture.difficulty, 0) / fixtures.length;
}

function scoreClass(score: number | null): string {
  if (score === null) return "text-muted";
  if (score <= 2.5) return "text-fpl-green";
  if (score <= 3.5) return "text-[#92400e]";
  return "text-fpl-red";
}
