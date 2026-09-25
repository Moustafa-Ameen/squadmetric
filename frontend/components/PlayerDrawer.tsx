"use client";

import Link from "next/link";
import {
  BarChart3,
  CalendarDays,
  CircleDollarSign,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingUp,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getCaptaincyPredictions,
  getFixtureTicker,
  getPlayerCatalog,
  getPlayerHistory,
  getPlayers,
} from "@/lib/api";
import { persistWatchlist, readWatchlist } from "@/lib/accountStorage";
import { normalized, points, positionCode } from "@/lib/format";
import type { CaptainPick, FixtureTick, Player, PlayerHistoryPoint } from "@/lib/types";
import { useDrawer } from "@/context/DrawerContext";
import { StartLikelihood } from "./StartLikelihood";

type ChartRange = 3 | 5 | 10;
const chartRanges: ChartRange[] = [3, 5, 10];

export function PlayerDrawer() {
  const { playerName, closeDrawer } = useDrawer();
  const [player, setPlayer] = useState<Player | null>(null);
  const [prediction, setPrediction] = useState<CaptainPick | null>(null);
  const [history, setHistory] = useState<PlayerHistoryPoint[]>([]);
  const [fixtures, setFixtures] = useState<FixtureTick | null>(null);
  const [captainRank, setCaptainRank] = useState<number | null>(null);
  const [watching, setWatching] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [chartRange, setChartRange] = useState<ChartRange>(3);

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
      setChartRange(3);
    });

    Promise.allSettled([
      getPlayers({ limit: 1000 }).catch(() => getPlayerCatalog()),
      getCaptaincyPredictions(),
      getPlayerHistory(playerName),
      getFixtureTicker(),
    ]).then(([playersResult, predictionsResult, historyResult, fixturesResult]) => {
      if (cancelled) return;
      const players = playersResult.status === "fulfilled" ? playersResult.value : [];
      const predictions = predictionsResult.status === "fulfilled" ? predictionsResult.value : [];
      const historyRows = historyResult.status === "fulfilled" ? historyResult.value : [];
      const fixtureRows = fixturesResult.status === "fulfilled" ? fixturesResult.value : [];
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
    }).finally(() => {
      if (!cancelled) setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [playerName]);

  useEffect(() => {
    if (!playerName) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDrawer();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeDrawer, playerName]);

  if (!playerName) return null;

  const displayPlayer = (player ?? { name: playerName, team: "-", position: "-", price: 0 }) as Player;
  const teamCode = displayPlayer.team_code ?? 1;
  const adjusted = prediction?.expected_points ?? displayPlayer.captain_rank_score;
  const availableHistory = history.length;
  const availableRanges = chartRanges.filter((range) => range <= availableHistory);
  const effectiveRange = availableRanges.includes(chartRange)
    ? chartRange
    : availableRanges.at(-1) ?? Math.max(1, availableHistory);
  const captainBadge =
    captainRank && captainRank <= 5
      ? "Top captain pick"
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
        className="absolute inset-0 bg-slate-950/45 backdrop-blur-[2px]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-drawer-title"
        className="drawer-panel absolute right-0 top-0 h-full w-full max-w-[560px] translate-x-0 overflow-x-hidden overflow-y-auto border-l border-slate-200 bg-slate-50 shadow-[-24px_0_70px_rgba(15,23,42,0.18)]"
      >
        <button
          type="button"
          onClick={closeDrawer}
          className="absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-slate-500 shadow-sm backdrop-blur hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>

        {isLoading ? (
          <PlayerDrawerSkeleton />
        ) : (
          <>
            <header className="border-b border-slate-200 bg-[radial-gradient(circle_at_top_right,rgba(109,62,234,0.12),transparent_45%),linear-gradient(135deg,#ffffff_0%,#f4fbf8_100%)] px-5 pb-6 pt-7 sm:px-7">
              <div className="flex items-center gap-4 pr-12 sm:gap-5">
                <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-3xl border border-white bg-white/85 p-2 shadow-[0_14px_35px_rgba(15,23,42,0.10)]">
                  <img
                    src={`https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCode}-66.png`}
                    width={88}
                    height={88}
                    alt={`${displayPlayer.team} kit`}
                    className="h-20 w-20 object-contain"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-extrabold uppercase tracking-[0.16em] text-emerald-700">
                    {displayPlayer.team} · {positionCode(displayPlayer.position)}
                  </p>
                  <h2 id="player-drawer-title" className="mt-1 text-2xl font-black tracking-tight text-slate-950 sm:text-[28px]">
                    {displayPlayer.name}
                  </h2>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-extrabold text-slate-900 shadow-sm">
                      <CircleDollarSign className="h-4 w-4 text-emerald-700" />
                      £{points(displayPlayer.price)}m
                    </span>
                    {captainBadge ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-100 px-3 py-1.5 text-xs font-extrabold text-violet-800">
                        <Sparkles className="h-3.5 w-3.5" />
                        {captainBadge}
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
            </header>

            <div className="space-y-5 px-4 py-5 sm:px-7 sm:py-6">
              <section aria-label="Player summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <MiniStat label="Expected" value={points(adjusted)} suffix="xP" tone="violet" />
                <MiniStat label="Start chance" value={<StartLikelihood value={displayPlayer.start_likelihood} />} tone="green" />
                <MiniStat label="Form" value={points(displayPlayer.form)} tone="amber" />
                <MiniStat label="Season points" value={points(displayPlayer.total_points, 0)} tone="slate" />
              </section>

              <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)] sm:p-5" aria-labelledby="recent-performance-title">
                <div className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-violet-600" />
                      <h3 id="recent-performance-title" className="font-extrabold text-slate-950">Recent performance</h3>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{rangeSummary(effectiveRange, availableHistory)}</p>
                  </div>
                  {availableRanges.length ? (
                    <div className="inline-flex w-fit rounded-xl bg-slate-100 p-1" aria-label="Chart gameweek range">
                      {availableRanges.map((range) => (
                        <button
                          type="button"
                          key={range}
                          onClick={() => setChartRange(range)}
                          aria-pressed={effectiveRange === range}
                          className={`min-w-10 rounded-lg px-3 py-1.5 text-xs font-extrabold ${
                            effectiveRange === range
                              ? "bg-white text-violet-700 shadow-sm"
                              : "text-slate-500 hover:text-slate-900"
                          }`}
                        >
                          {range}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>

                {availableHistory ? (
                  <div className="mt-5 grid gap-6">
                    <Trend title="Price" data={history} dataKey="price" color="#059669" range={effectiveRange} />
                    <Trend title="Points per gameweek" data={history} dataKey="total_points" color="#6d3eea" range={effectiveRange} />
                  </div>
                ) : (
                  <div className="mt-5 rounded-2xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                    Completed-gameweek history will appear here once it is available.
                  </div>
                )}
              </section>

              <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.05)] sm:p-5" aria-labelledby="upcoming-fixtures-title">
                <div className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-emerald-700" />
                  <h3 id="upcoming-fixtures-title" className="font-extrabold text-slate-950">Next fixtures</h3>
                </div>
                <div className="mt-4 grid gap-2.5 sm:grid-cols-3">
                  {(fixtures?.fixtures ?? []).slice(0, 3).map((fixture, index) => (
                    <FixtureCard key={`${fixture.gw}-${index}`} fixture={fixture} />
                  ))}
                </div>
                {!fixtures?.fixtures.length ? (
                  <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">Fixture schedule pending.</div>
                ) : null}
              </section>

              <p className="px-1 text-center text-xs leading-5 text-slate-500">
                Projections use the latest completed gameweeks, current fixtures, and estimated minutes.
              </p>

              <div className="grid gap-3 pb-2 sm:grid-cols-2">
                <button type="button" onClick={toggleWatchlist} className="sm-primary-button justify-center px-4 py-3">
                  <Star className={`h-4 w-4 ${watching ? "fill-current" : ""}`} />
                  {watching ? "On watchlist" : "Add to watchlist"}
                </button>
                <Link href="/captain" onClick={closeDrawer} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-extrabold text-slate-800 shadow-sm hover:border-violet-200 hover:bg-violet-50 hover:text-violet-800">
                  <ShieldCheck className="h-4 w-4" />
                  Compare captain picks
                </Link>
              </div>
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
    <div aria-busy="true" className="px-5 py-7 sm:px-7">
      <div className="flex gap-5 pr-12">
        <div className="skeleton h-24 w-24 rounded-3xl" />
        <div className="flex-1 pt-3">
          <div className="skeleton h-4 w-28" />
          <div className="skeleton mt-3 h-7 w-52 [animation-delay:100ms]" />
          <div className="skeleton mt-3 h-8 w-24 [animation-delay:150ms]" />
        </div>
      </div>
      <div className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="skeleton h-24 rounded-2xl" style={{ animationDelay: `${index * 75}ms` }} />
        ))}
      </div>
      <div className="skeleton mt-5 h-[460px] rounded-3xl [animation-delay:300ms]" />
    </div>
  );
}

function rangeSummary(range: number, available: number): string {
  if (!available) return "No completed-gameweek history yet";
  const shown = Math.min(range, available);
  return `${shown} most recent completed gameweek${shown === 1 ? "" : "s"}`;
}

function MiniStat({
  label,
  value,
  suffix,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  suffix?: string;
  tone: "violet" | "green" | "amber" | "slate";
}) {
  const tones = {
    violet: "border-violet-100 bg-violet-50/70 text-violet-800",
    green: "border-emerald-100 bg-emerald-50/70 text-emerald-800",
    amber: "border-amber-100 bg-amber-50/70 text-amber-900",
    slate: "border-slate-200 bg-white text-slate-900",
  };
  return (
    <div className={`flex min-h-24 flex-col items-center justify-center rounded-2xl border p-3 text-center ${tones[tone]}`}>
      <div className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="mt-2 flex items-baseline justify-center gap-1 text-xl font-black leading-none">
        {value}
        {suffix ? <span className="text-[10px] font-bold uppercase tracking-wide opacity-60">{suffix}</span> : null}
      </div>
    </div>
  );
}

function FixtureCard({ fixture }: { fixture: FixtureTick["fixtures"][number] }) {
  const label = fixture.difficulty <= 2 ? "Favourable" : fixture.difficulty === 3 ? "Balanced" : "Tough";
  const tone = fixture.difficulty <= 2
    ? "bg-emerald-100 text-emerald-800"
    : fixture.difficulty === 3
      ? "bg-amber-100 text-amber-900"
      : "bg-rose-100 text-rose-800";
  return (
    <article className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3.5 text-center">
      <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">GW{fixture.gw}</div>
      <div className="mt-1 text-base font-black text-slate-950">{fixture.opponent}</div>
      <div className="mt-0.5 text-xs font-semibold text-slate-500">{fixture.home ? "Home" : "Away"}</div>
      <span className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-[10px] font-extrabold ${tone}`}>
        {label} · FDR {fixture.difficulty}
      </span>
    </article>
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
  range: number;
}) {
  const chartData = data.slice(-range);
  const values = chartData.map((row) => Number(row[dataKey])).filter((value) => Number.isFinite(value));
  const isPrice = dataKey === "price";
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : isPrice ? 1 : 10;
  const padding = isPrice ? 0.1 : Math.max(1, Math.ceil((maxValue - minValue) * 0.15));
  const min = Math.max(0, minValue - padding);
  const max = maxValue + padding;
  const ticks = [min, (min + max) / 2, max];
  const gradientId = `player-${dataKey}-gradient`;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-extrabold text-slate-800">
          {isPrice ? <CircleDollarSign className="h-4 w-4 text-emerald-600" /> : <BarChart3 className="h-4 w-4 text-violet-600" />}
          {title}
        </div>
        <span className="text-xs font-bold text-slate-500">
          {isPrice ? `£${Number(chartData.at(-1)?.price ?? 0).toFixed(1)}m` : `${Number(chartData.at(-1)?.total_points ?? 0)} pts`}
        </span>
      </div>
      <div className="h-[190px] rounded-2xl bg-slate-50 px-1 py-3 sm:px-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.24} />
                <stop offset="95%" stopColor={color} stopOpacity={0.015} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#e2e8f0" strokeDasharray="3 5" />
            <XAxis
              dataKey="gw"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#64748b", fontSize: 11, fontWeight: 700 }}
              tickFormatter={(value) => `GW${value}`}
              dy={8}
            />
            <YAxis
              domain={[min, max]}
              ticks={ticks}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#94a3b8", fontSize: 10 }}
              tickFormatter={(value) => isPrice ? `£${Number(value).toFixed(1)}` : String(Math.round(Number(value)))}
              width={44}
            />
            <Tooltip
              cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: "4 4" }}
              contentStyle={{
                background: "#ffffff",
                border: "1px solid #e2e8f0",
                borderRadius: 12,
                boxShadow: "0 12px 32px rgba(15,23,42,0.12)",
                color: "#0f172a",
                fontSize: 12,
              }}
              formatter={(value) =>
                isPrice
                  ? [`£${Number(value).toFixed(1)}m`, "Price"]
                  : [`${Number(value)} pts`, "Points"]
              }
              labelFormatter={(value) => `Gameweek ${value}`}
            />
            <Area
              dataKey={dataKey}
              type="monotone"
              stroke={color}
              strokeWidth={3}
              fill={`url(#${gradientId})`}
              dot={{ r: 4, fill: "#ffffff", stroke: color, strokeWidth: 2.5 }}
              activeDot={{ r: 6, fill: color, stroke: "#ffffff", strokeWidth: 3 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
