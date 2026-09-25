"use client";

import { LayoutGrid, Search, Star, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { StartLikelihood } from "@/components/StartLikelihood";
import { useDrawer } from "@/context/DrawerContext";
import { getPlayerCatalog, getPlayers, getSeasonState } from "@/lib/api";
import { persistWatchlist, readWatchlist } from "@/lib/accountStorage";
import { kitUrl, matchesPlayerSearch, points, positionCode, price } from "@/lib/format";
import type { Player, SeasonState } from "@/lib/types";

type ViewMode = "table" | "card";
type ListMode = "all" | "watchlist";
type SortKey = "name" | "team" | "position" | "price" | "ppg" | "form" | "transfer_rank_score" | "start_likelihood" | "value";
type PositionFilter = "All" | "GK" | "DEF" | "MID" | "FWD";

const positions: PositionFilter[] = ["All", "GK", "DEF", "MID", "FWD"];
const columns: { label: string; key: SortKey; align?: "right" }[] = [
  { label: "Player", key: "name" },
  { label: "Team", key: "team" },
  { label: "Pos", key: "position" },
  { label: "Price", key: "price", align: "right" },
  { label: "PPG", key: "ppg", align: "right" },
  { label: "Form", key: "form", align: "right" },
  { label: "Recommendation", key: "transfer_rank_score", align: "right" },
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
  const [sortKey, setSortKey] = useState<SortKey>("transfer_rank_score");
  const [ascending, setAscending] = useState(false);
  const [page, setPage] = useState(1);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [catalogOnly, setCatalogOnly] = useState(false);

  useEffect(() => {
    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        if (state.recommendations_ready) return getPlayers({ limit: 1000 });
        setCatalogOnly(true);
        setSortKey("ppg");
        return getPlayerCatalog(1000);
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
      groups.set(code, [...(groups.get(code) ?? []), transferRating(player)]);
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
      .filter((player) => matchesPlayerSearch(search, `${player.name} ${player.team}`))
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
  if (error) return <ErrorState />;
  if (!players.length) return <EmptyState />;

  return (
    <div className="space-y-6">
      <SectionHeader title="Players" subtitle="Search every current FPL player, compare the signals that matter, and save a shortlist." />

      {catalogOnly && seasonState ? (
        <div className="rounded-2xl border border-violet-200 bg-violet-50 px-5 py-4 text-sm leading-6 text-violet-950">
          Official players, clubs, positions and prices are still available below. Model rankings are hidden until the latest data refresh passes validation.
        </div>
      ) : null}

      <Panel>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex rounded-xl border border-slate-200 bg-slate-50 p-1">
            <Toggle active={listMode === "all"} onClick={() => setListMode("all")}>
              All Players
            </Toggle>
            <Toggle active={listMode === "watchlist"} onClick={() => setListMode("watchlist")}>
              <Star className="mr-1 inline h-3 w-3" />
              Watchlist ({watchlist.length})
            </Toggle>
          </div>
          <div className="flex rounded-xl border border-slate-200 bg-slate-50 p-1">
            <IconToggle active={view === "card"} onClick={() => setView("card")} label="Cards">
              <LayoutGrid className="h-4 w-4" />
            </IconToggle>
            <IconToggle active={view === "table"} onClick={() => setView("table")} label="Table">
              <Table2 className="h-4 w-4" />
            </IconToggle>
          </div>
        </div>

        <div className="sticky top-3 z-10 mb-5 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur">
          <div className="grid gap-3 xl:grid-cols-[minmax(220px,1fr)_auto_auto_auto] xl:items-center">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="Search player or club…"
                className="h-10 w-full rounded-xl border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-950 outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-100"
              />
            </label>
            <div className="flex rounded-xl border border-slate-200 bg-slate-50 p-1">
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
                className="h-10 w-24 rounded-xl border border-slate-300 bg-white px-3 text-xs text-slate-950 outline-none focus:border-violet-500"
              />
              <input
                value={maxPrice}
                onChange={(event) => {
                  setMaxPrice(event.target.value);
                  setPage(1);
                }}
                placeholder="Max £"
                className="h-10 w-24 rounded-xl border border-slate-300 bg-white px-3 text-xs text-slate-950 outline-none focus:border-violet-500"
              />
            </div>
            <select
              aria-label="Sort players"
              value={sortKey}
              onChange={(event) => {
                setSortKey(event.target.value as SortKey);
                setPage(1);
              }}
              className="h-10 rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none focus:border-violet-500"
            >
              <option value="transfer_rank_score">Sort by recommendation</option>
              <option value="price">Sort by price</option>
              <option value="ppg">Sort by PPG</option>
              <option value="form">Sort by form</option>
              <option value="start_likelihood">Sort by start %</option>
              <option value="value">Sort by value</option>
              <option value="name">Sort by name</option>
            </select>
          </div>
        </div>

        {!filtered.length ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-600">
            {listMode === "watchlist" ? "No players watched yet. Select the star beside any player to save them here." : "No players match these filters. Clear the search or widen the price range."}
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

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
          <span>
            Showing {visible.length} of {filtered.length} players · Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
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
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
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
              className={`cursor-pointer border-b border-slate-200 hover:bg-violet-50 ${
                index % 2 === 0 ? "bg-white" : "bg-slate-50/60"
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
              <td className="py-3 pr-3 font-bold text-slate-950">{player.name}</td>
              <td className="py-3 pr-3 text-slate-600">{player.team}</td>
              <td className="py-3 pr-3 text-slate-600">{positionCode(player.position)}</td>
              <td className="py-3 pr-3 text-right font-semibold text-slate-900">{price(player.price)}</td>
              <td className="py-3 pr-3 text-right font-semibold text-slate-900">{points(player.ppg)}</td>
              <td className="py-3 pr-3 text-right font-semibold text-slate-900">{points(player.form)}</td>
              <td className={`py-3 pr-3 text-right font-extrabold ${predictedClass(player, averages)}`}>
                {player.metrics_available === false ? "—" : points(transferRating(player))}
              </td>
              <td className="py-3 pr-3 text-right">
                <StartLikelihood value={player.start_likelihood} />
              </td>
              <td className="py-3 pr-3 text-right font-semibold text-slate-900">{points(player.value)}</td>
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
    <div className="relative rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-[0_8px_24px_rgba(15,23,42,0.05)] transition hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-lg">
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
        <div className="mt-3 truncate text-sm font-extrabold text-slate-950">{player.name}</div>
        <div className="mt-1 text-xs text-slate-500">{player.team} · {positionCode(player.position)}</div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <CardMetric label="Recommendation" value={player.metrics_available === false ? "Refresh needed" : points(transferRating(player))} />
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
        active ? "bg-violet-600 text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-950"
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
        active ? "bg-violet-600 text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-950"
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
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-extrabold text-slate-950">{value}</div>
    </div>
  );
}

function transferRating(player: Player): number {
  return player.transfer_rank_score ?? 0;
}

function predictedClass(player: Player, averages: Record<string, number>): string {
  const average = averages[positionCode(player.position)] ?? 0;
  return transferRating(player) >= average ? "text-emerald-700" : "text-slate-500";
}

function valueForSort(player: Player, key: SortKey): string | number {
  if (key === "transfer_rank_score") return transferRating(player);
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
