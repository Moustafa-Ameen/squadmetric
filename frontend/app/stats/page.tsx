"use client";

import { LayoutGrid, Search, Star, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/LoadingState";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { StartLikelihood } from "@/components/StartLikelihood";
import { useDrawer } from "@/context/DrawerContext";
import { getPlayers, getSeasonState } from "@/lib/api";
import { persistWatchlist, readWatchlist } from "@/lib/accountStorage";
import { kitUrl, matchesPlayerSearch, points, positionCode, price } from "@/lib/format";
import type { Player, SeasonState } from "@/lib/types";

type ViewMode = "table" | "card";
type ListMode = "all" | "watchlist";
type SortKey = "name" | "team" | "position" | "price" | "ppg" | "form" | "captain_rank_score" | "start_likelihood" | "value";
type PositionFilter = "All" | "GK" | "DEF" | "MID" | "FWD";

const positions: PositionFilter[] = ["All", "GK", "DEF", "MID", "FWD"];
const columns: { label: string; key: SortKey; align?: "right" }[] = [
  { label: "Player", key: "name" },
  { label: "Team", key: "team" },
  { label: "Pos", key: "position" },
  { label: "Price", key: "price", align: "right" },
  { label: "PPG", key: "ppg", align: "right" },
  { label: "Form", key: "form", align: "right" },
  { label: "Captain rank", key: "captain_rank_score", align: "right" },
  { label: "Start %", key: "start_likelihood", align: "right" },
  { label: "Value", key: "value", align: "right" },
];

export default function StatsPage() {
  const { openDrawer } = useDrawer();
  const [players, setPlayers] = useState<Player[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [listMode, setListMode] = useState<ListMode>("all");
  const [view, setView] = useState<ViewMode>("table");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState<PositionFilter>("All");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("captain_rank_score");
  const [ascending, setAscending] = useState(false);
  const [page, setPage] = useState(1);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);

  useEffect(() => {
    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        return state.recommendations_ready ? getPlayers({ limit: 1000 }) : [];
      })
      .then(setPlayers)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
    queueMicrotask(() => {
      setWatchlist(readWatchlist());
    });
  }, []);

  const positionAverages = useMemo(() => {
    const groups = new Map<string, number[]>();
    for (const player of players) {
      const code = positionCode(player.position);
      groups.set(code, [...(groups.get(code) ?? []), captainRank(player)]);
    }
    return Object.fromEntries(
      [...groups.entries()].map(([key, values]) => [key, values.reduce((sum, value) => sum + value, 0) / values.length]),
    );
  }, [players]);

  const filtered = useMemo(() => {
    const min = minPrice ? Number(minPrice) : Number.NEGATIVE_INFINITY;
    const max = maxPrice ? Number(maxPrice) : Number.POSITIVE_INFINITY;
    return players
      .filter((player) => listMode === "all" || watchlist.includes(player.name))
      .filter((player) => position === "All" || positionCode(player.position) === position)
      .filter((player) => matchesPlayerSearch(search, player.name))
      .filter((player) => player.price >= min && player.price <= max)
      .sort((a, b) => compareValues(valueForSort(a, sortKey), valueForSort(b, sortKey), ascending));
  }, [ascending, listMode, maxPrice, minPrice, players, position, search, sortKey, watchlist]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / 25));
  const visible = filtered.slice((page - 1) * 25, page * 25);

  function sortBy(key: SortKey) {
    if (key === sortKey) {
      setAscending((value) => !value);
    } else {
      setSortKey(key);
      setAscending(false);
    }
    setPage(1);
  }

  function toggleWatch(player: Player) {
    setWatchlist((current) => {
      const next = current.includes(player.name)
        ? current.filter((item) => item !== player.name)
        : [...current, player.name];
      persistWatchlist(players.filter((candidate) => next.includes(candidate.name)));
      return next;
    });
  }

  if (loading) return <TableSkeleton />;
  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Player Stats" subtitle="Current player rankings are awaiting a validated refresh" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }
  if (error) return <ErrorState />;
  if (!players.length) return <EmptyState />;

  return (
    <div className="space-y-6">
      <SectionHeader title="Let me find any player." subtitle="Search, filter, compare, and build a watchlist." />

      <Panel>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
            <Toggle active={listMode === "all"} onClick={() => setListMode("all")}>
              All Players
            </Toggle>
            <Toggle active={listMode === "watchlist"} onClick={() => setListMode("watchlist")}>
              <Star className="mr-1 inline h-3 w-3" />
              Watchlist ({watchlist.length})
            </Toggle>
          </div>
          <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
            <IconToggle active={view === "card"} onClick={() => setView("card")} label="Cards">
              <LayoutGrid className="h-4 w-4" />
            </IconToggle>
            <IconToggle active={view === "table"} onClick={() => setView("table")} label="Table">
              <Table2 className="h-4 w-4" />
            </IconToggle>
          </div>
        </div>

        <div className="sticky top-3 z-10 mb-5 rounded-lg border border-fpl-border bg-[#101514]/95 p-3 backdrop-blur">
          <div className="grid gap-3 xl:grid-cols-[minmax(220px,1fr)_auto_auto_auto] xl:items-center">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="Search player name..."
                className="h-10 w-full rounded-lg border border-fpl-border bg-fpl-raised pl-9 pr-3 text-sm text-primary outline-none focus:border-fpl-green"
              />
            </label>
            <div className="flex rounded-lg border border-fpl-border bg-fpl-raised p-1">
              {positions.map((item) => (
                <Toggle
                  key={item}
                  active={position === item}
                  onClick={() => {
                    setPosition(item);
                    setPage(1);
                  }}
                >
                  {item}
                </Toggle>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={minPrice}
                onChange={(event) => {
                  setMinPrice(event.target.value);
                  setPage(1);
                }}
                placeholder="Min £"
                className="h-10 w-24 rounded-lg border border-fpl-border bg-fpl-raised px-3 text-xs text-primary outline-none focus:border-fpl-green"
              />
              <input
                value={maxPrice}
                onChange={(event) => {
                  setMaxPrice(event.target.value);
                  setPage(1);
                }}
                placeholder="Max £"
                className="h-10 w-24 rounded-lg border border-fpl-border bg-fpl-raised px-3 text-xs text-primary outline-none focus:border-fpl-green"
              />
            </div>
            <select
              value={sortKey}
              onChange={(event) => {
                setSortKey(event.target.value as SortKey);
                setPage(1);
              }}
              className="h-10 rounded-lg border border-fpl-border bg-fpl-raised px-3 text-sm text-primary outline-none focus:border-fpl-green"
            >
              <option value="captain_rank_score">Sort by captain rank</option>
              <option value="price">Sort by price</option>
              <option value="ppg">Sort by PPG</option>
              <option value="form">Sort by form</option>
              <option value="start_likelihood">Sort by start %</option>
              <option value="value">Sort by value</option>
              <option value="name">Sort by name</option>
            </select>
          </div>
        </div>

        {listMode === "watchlist" && !filtered.length ? (
          <div className="rounded-lg border border-fpl-border bg-fpl-raised p-5 text-sm text-muted">
            No players watched yet. Click ★ on any player to add them here.
          </div>
        ) : view === "table" ? (
          <PlayerTable
            players={visible}
            watchlist={watchlist}
            averages={positionAverages}
            sortKey={sortKey}
            ascending={ascending}
            onSort={sortBy}
            onToggleWatch={toggleWatch}
            onSelect={openDrawer}
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((player) => (
              <PlayerCard
                key={player.name}
                player={player}
                watched={watchlist.includes(player.name)}
                onToggleWatch={toggleWatch}
                onSelect={openDrawer}
              />
            ))}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
          <span>
            Showing {visible.length} of {filtered.length} players · Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              className="rounded-lg border border-fpl-border px-3 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              className="rounded-lg border border-fpl-border px-3 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function PlayerTable({
  players,
  watchlist,
  averages,
  sortKey,
  ascending,
  onSort,
  onToggleWatch,
  onSelect,
}: {
  players: Player[];
  watchlist: string[];
  averages: Record<string, number>;
  sortKey: SortKey;
  ascending: boolean;
  onSort: (key: SortKey) => void;
  onToggleWatch: (player: Player) => void;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-fpl-card text-xs uppercase text-muted">
          <tr>
            <th className="pb-3 pr-3">★</th>
            <th className="pb-3 pr-3">Kit</th>
            {columns.map((column) => (
              <th key={column.key} className={`pb-3 pr-3 ${column.align === "right" ? "text-right" : ""}`}>
                <button type="button" onClick={() => onSort(column.key)} className="hover:text-primary">
                  {column.label}
                  {sortKey === column.key ? (ascending ? " ↑" : " ↓") : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {players.map((player, index) => (
            <tr
              key={player.name}
              onClick={() => onSelect(player.name)}
              className={`cursor-pointer border-b border-fpl-border hover:bg-fpl-green/5 ${
                index % 2 === 0 ? "bg-[#161616]" : "bg-[#181818]"
              }`}
            >
              <td className="py-3 pr-3">
                <StarButton
                  active={watchlist.includes(player.name)}
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleWatch(player);
                  }}
                />
              </td>
              <td className="py-3 pr-3">
                <img src={kitUrl(player.team_code)} alt={`${player.team} kit`} className="h-10 w-10 object-contain" />
              </td>
              <td className="py-3 pr-3 font-semibold text-primary">{player.name}</td>
              <td className="py-3 pr-3 text-muted">{player.team}</td>
              <td className="py-3 pr-3 text-muted">{positionCode(player.position)}</td>
              <td className="py-3 pr-3 text-right font-mono text-primary">{price(player.price)}</td>
              <td className="py-3 pr-3 text-right font-mono text-primary">{points(player.ppg)}</td>
              <td className="py-3 pr-3 text-right font-mono text-primary">{points(player.form)}</td>
              <td className={`py-3 pr-3 text-right font-mono font-bold ${predictedClass(player, averages)}`}>
                {points(captainRank(player))}
              </td>
              <td className="py-3 pr-3 text-right">
                <StartLikelihood value={player.start_likelihood} />
              </td>
              <td className="py-3 pr-3 text-right font-mono text-primary">{points(player.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlayerCard({
  player,
  watched,
  onToggleWatch,
  onSelect,
}: {
  player: Player;
  watched: boolean;
  onToggleWatch: (player: Player) => void;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="relative rounded-lg border border-[rgba(123,47,190,0.2)] bg-[#161616] p-4 text-center transition hover:scale-[1.02] hover:border-fpl-green">
      <button
        type="button"
        onClick={() => onToggleWatch(player)}
        aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
        className="absolute right-3 top-3"
      >
        <Star className={`h-4 w-4 ${watched ? "fill-fpl-gold text-fpl-gold" : "text-muted"}`} />
      </button>
      <button type="button" onClick={() => onSelect(player.name)} className="w-full text-center">
        <img src={kitUrl(player.team_code)} alt={`${player.team} kit`} className="mx-auto h-[52px] w-[62px] object-contain" />
        <div className="mt-3 truncate text-sm font-bold text-primary">{player.name}</div>
        <div className="mt-1 text-xs text-muted">{player.team}</div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <CardMetric label="Captain rank" value={points(captainRank(player))} />
          <CardMetric label="Price" value={price(player.price)} />
          <div>
            <div className="text-[11px] text-muted">Start %</div>
            <div className="mt-1">
              <StartLikelihood value={player.start_likelihood} />
            </div>
          </div>
        </div>
      </button>
    </div>
  );
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
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

function IconToggle({
  active,
  onClick,
  label,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 ${
        active ? "bg-fpl-green text-fpl-dark" : "text-secondary hover:text-primary"
      }`}
    >
      {children}
    </button>
  );
}

function StarButton({ active, onClick }: { active: boolean; onClick: (event: React.MouseEvent) => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={active ? "Remove from watchlist" : "Add to watchlist"}>
      <Star className={`h-4 w-4 ${active ? "fill-fpl-gold text-fpl-gold" : "text-muted"}`} />
    </button>
  );
}

function CardMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm font-bold text-primary">{value}</div>
    </div>
  );
}

function captainRank(player: Player): number {
  return player.captain_rank_score ?? 0;
}

function predictedClass(player: Player, averages: Record<string, number>): string {
  const average = averages[positionCode(player.position)] ?? 0;
  return captainRank(player) >= average ? "text-fpl-green" : "text-fpl-red";
}

function valueForSort(player: Player, key: SortKey): string | number {
  if (key === "captain_rank_score") return captainRank(player);
  if (key === "position") return positionCode(player.position);
  return player[key] as string | number;
}

function compareValues(a: string | number, b: string | number, ascending: boolean): number {
  const result =
    typeof a === "number" && typeof b === "number"
      ? a - b
      : String(a).localeCompare(String(b));
  return ascending ? result : -result;
}
