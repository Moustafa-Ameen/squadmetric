"use client";

import Link from "next/link";
import { Star, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getCaptaincyPredictions,
  getFixtureTicker,
  getPlayerHistory,
  getPlayers,
} from "@/lib/api";
import { persistWatchlist, readWatchlist } from "@/lib/accountStorage";
import { normalized, points, positionCode } from "@/lib/format";
import type { CaptainPick, FixtureTick, Player, PlayerHistoryPoint } from "@/lib/types";
import { useDrawer } from "@/context/DrawerContext";
import { FixtureChip } from "./FixtureChip";
import { StartLikelihood } from "./StartLikelihood";

type ChartRange = 5 | 10 | 20 | "All";
const chartRanges: ChartRange[] = [5, 10, 20, "All"];

export function PlayerDrawer() {
  const { playerName, closeDrawer } = useDrawer();
  const [player, setPlayer] = useState<Player | null>(null);
  const [prediction, setPrediction] = useState<CaptainPick | null>(null);
  const [history, setHistory] = useState<PlayerHistoryPoint[]>([]);
  const [fixtures, setFixtures] = useState<FixtureTick | null>(null);
  const [captainRank, setCaptainRank] = useState<number | null>(null);
  const [watching, setWatching] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [chartRange, setChartRange] = useState<ChartRange>(10);

  useEffect(() => {
    if (!playerName) return;
    let cancelled = false;
    queueMicrotask(() => {
      setIsLoading(true);
      setPlayer(null);
      setPrediction(null);
      setHistory([]);
      setFixtures(null);
      setCaptainRank(null);
      setWatching(false);
    });

    Promise.all([
      getPlayers({ limit: 1000 }),
      getCaptaincyPredictions(),
      getPlayerHistory(playerName),
      getFixtureTicker(),
    ]).then(([players, predictions, historyRows, fixtureRows]) => {
      if (cancelled) return;
      const found =
        players.find((row) => normalized(row.name) === normalized(playerName)) ??
        players.find((row) => normalized(row.name).includes(normalized(playerName)));
      const idRankIndex = found
        ? predictions.findIndex((row) => playerKey(row) === playerKey(found))
        : -1;
      const rankIndex = idRankIndex >= 0
        ? idRankIndex
        : predictions.findIndex((row) => normalized(row.name) === normalized(playerName));
      setPlayer(found ?? null);
      setPrediction(predictions[rankIndex] ?? null);
      setCaptainRank(rankIndex >= 0 ? rankIndex + 1 : null);
      setHistory(historyRows);
      setFixtures(
        found
          ? fixtureRows.find((row) => row.team_short === found.team || row.team === found.team) ?? null
          : null,
      );
      const watchlist = readWatchlist();
      setWatching(watchlist.includes(playerName));
    })
      .catch(() => {
        if (cancelled) return;
        setPlayer(null);
        setPrediction(null);
        setHistory([]);
        setFixtures(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [playerName]);

  if (!playerName) return null;

  const displayPlayer = (player ?? { name: playerName, team: "-", position: "-", price: 0 }) as Player;
  const teamCode = displayPlayer.team_code ?? 1;
  const adjusted = prediction?.expected_points ?? displayPlayer.captain_rank_score;
  const availableHistory = history.length;
  const captainBadge =
    captainRank && captainRank <= 5
      ? "Top pick"
      : captainRank && captainRank <= 10
        ? "Captain contender"
        : null;

  function toggleWatchlist() {
    const watchlist = readWatchlist();
    const next = watching
      ? watchlist.filter((item) => item !== playerName)
      : [...new Set([...watchlist, playerName])].filter((name): name is string => Boolean(name));
    persistWatchlist(next.map((name) => ({
      name,
      element_id: name === playerName ? displayPlayer.element_id : undefined,
    })));
    setWatching(!watching);
  }

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close player drawer"
        onClick={closeDrawer}
        className="absolute inset-0 bg-black/70"
      />
      <aside className="drawer-panel absolute right-0 top-0 h-full w-full max-w-[400px] translate-x-0 overflow-y-auto border-l border-fpl-border bg-fpl-card p-5 shadow-2xl">
        <button
          type="button"
          onClick={closeDrawer}
          className="absolute right-4 top-4 rounded-lg p-2 text-muted hover:bg-fpl-raised hover:text-primary"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {isLoading ? (
          <PlayerDrawerSkeleton />
        ) : (
          <>
            <div className="flex gap-4 pr-8">
              <img
                src={`https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCode}-66.png`}
                width={80}
                height={80}
                alt={`${displayPlayer.team} kit`}
                className="h-20 w-20 object-contain"
              />
              <div>
                <h2 className="text-xl font-bold text-primary">{displayPlayer.name}</h2>
                <p className="mt-1 text-sm text-secondary">
                  {displayPlayer.team} - {positionCode(displayPlayer.position)}
                </p>
                <p className="mt-2 font-mono text-lg font-bold text-primary">
                  £{points(displayPlayer.price)}m
                </p>
                {captainBadge ? (
                  <span className="mt-2 inline-flex rounded-full border border-fpl-green bg-fpl-green/10 px-2 py-1 text-xs font-bold text-fpl-green">
                    {captainBadge}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="mt-6 grid grid-cols-4 gap-2">
              <MiniStat label="Expected points" value={points(adjusted)} />
              <MiniStat label="Start" value={<StartLikelihood value={displayPlayer.start_likelihood} />} />
              <MiniStat label="Form" value={points(displayPlayer.form)} />
              <MiniStat label="Points" value={points(displayPlayer.total_points, 0)} />
            </div>
            <p className="mt-2 text-[11px] italic text-muted">
              Predictions based on most recent available gameweek data
            </p>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-muted">{rangeSummary(chartRange, availableHistory)}</div>
              <div className="flex justify-end gap-1.5">
                {chartRanges.map((range) => (
                  <button
                    type="button"
                    key={range}
                    onClick={() => setChartRange(range)}
                    className={`h-7 rounded-full border px-2.5 text-xs ${
                      chartRange === range
                        ? "border-[rgba(0,255,135,0.3)] bg-fpl-green/15 text-fpl-green"
                        : "border-white/10 bg-[rgba(255,255,255,0.06)] text-secondary"
                    }`}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
            <Trend title="Price trend" data={history} dataKey="price" color="#00FF87" range={chartRange} />
            <Trend title="Points per GW" data={history} dataKey="total_points" color="#FFD700" range={chartRange} />

            <div className="mt-6">
              <h3 className="mb-3 text-sm font-semibold text-primary">Upcoming fixtures</h3>
              <div className="flex flex-wrap gap-2">
                {(fixtures?.fixtures ?? []).slice(0, 3).map((fixture, index) => (
                  <span
                    key={`${fixture.gw}-${index}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-fpl-border px-2 py-1 text-xs text-secondary"
                  >
                    {fixture.opponent} {fixture.home ? "H" : "A"}
                    <FixtureChip difficulty={fixture.difficulty} />
                  </span>
                ))}
                {!fixtures?.fixtures.length ? <span className="text-sm text-muted">Fixtures pending</span> : null}
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3">
              <button type="button" onClick={toggleWatchlist} className="fpl-button px-3 py-2 text-sm">
                <Star className="mr-1 inline h-4 w-4" />
                {watching ? "Watching" : "Add to watchlist"}
              </button>
              <Link href="/captain" onClick={closeDrawer} className="fpl-secondary-button px-3 py-2 text-center text-sm">
                Captain this week
              </Link>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

function playerKey(player: Pick<Player, "element_id" | "name"> | Pick<CaptainPick, "element_id" | "name">): string {
  return player.element_id ? `id:${player.element_id}` : `name:${normalized(player.name)}`;
}

function PlayerDrawerSkeleton() {
  return (
    <div aria-busy="true" className="pr-8">
      <div className="flex gap-4">
        <div className="skeleton skeleton-circle h-16 w-16" />
        <div className="flex-1 pt-2">
          <div className="skeleton h-5 w-44" />
          <div className="skeleton mt-3 h-3 w-28 [animation-delay:150ms]" />
        </div>
      </div>
      <div className="mt-6 grid grid-cols-4 gap-2">
        {[0, 1, 2, 3].map((index) => (
          <div
            key={index}
            className="skeleton h-[58px]"
            style={{ animationDelay: `${index * 75}ms` }}
          />
        ))}
      </div>
      <div className="skeleton mt-8 h-[200px] [animation-delay:300ms]" />
      <div className="skeleton mt-6 h-[180px] [animation-delay:300ms]" />
    </div>
  );
}

function rangeSummary(range: ChartRange, available: number): string {
  if (!available) return "No GW history available yet";
  if (range === "All") return `Showing all ${available} available GWs`;
  const shown = Math.min(range, available);
  return shown < range
    ? `Showing all ${available} available GWs`
    : `Showing last ${shown} of ${available} GWs`;
}

function MiniStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-fpl-border bg-fpl-raised p-2">
      <div className="text-[11px] uppercase tracking-[0.08em] text-muted">{label}</div>
      <div className="mt-1 font-mono text-lg font-bold text-primary">{value}</div>
    </div>
  );
}

function Trend({
  title,
  data,
  dataKey,
  color,
  range,
}: {
  title: string;
  data: PlayerHistoryPoint[];
  dataKey: "price" | "total_points";
  color: string;
  range: ChartRange;
}) {
  const chartData = range === "All" ? data : data.slice(-range);
  const values = chartData.map((row) => Number(row[dataKey])).filter((value) => Number.isFinite(value));
  const isPrice = dataKey === "price";
  const min = values.length ? Math.min(...values) - (isPrice ? 0.2 : 1) : 0;
  const max = values.length ? Math.max(...values) + (isPrice ? 0.2 : 1) : isPrice ? 1 : 10;
  const height = isPrice ? 200 : 180;
  const referenceValue = isPrice
    ? chartData[0]?.price
    : values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : undefined;

  return (
    <div className="mt-6">
      <h3 className="mb-2 text-sm font-semibold text-primary">{title}</h3>
      <div className="rounded-lg border border-fpl-border bg-fpl-raised p-2" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <XAxis
              dataKey="gw"
              hide
            />
            <YAxis
              domain={[min, max]}
              hide
            />
            <Tooltip
              contentStyle={{ background: "#161616", border: "1px solid #2A2A2A", color: "#FFFFFF" }}
              formatter={(value) =>
                isPrice
                  ? [`£${Number(value).toFixed(1)}m`, "Price"]
                  : [`${Number(value)} pts`, "Points"]
              }
              labelFormatter={(value) => `GW ${value}`}
            />
            {referenceValue !== undefined ? (
              <ReferenceLine y={referenceValue} stroke="#A0A0A0" strokeDasharray="4 4" />
            ) : null}
            <Line
              dataKey={dataKey}
              type="monotone"
              stroke={color}
              strokeWidth={2}
              dot={{ r: 2, fill: color }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
