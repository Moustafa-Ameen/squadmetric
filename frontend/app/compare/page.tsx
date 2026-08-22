"use client";

import { Info, Search, Scale, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { FixtureChip } from "@/components/FixtureChip";
import { DecisionStatusNotice } from "@/components/DecisionStatusNotice";
import { ErrorState, TableSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { comparePlayers, getPlayers, getSeasonState } from "@/lib/api";
import {
  displayPlayerName,
  displayTeam,
  displayTeamShort,
  kitUrl,
  matchesPlayerSearch,
  positionCode,
} from "@/lib/format";
import type { ComparisonPlayer, Player, PlayerComparisonResponse, SeasonState } from "@/lib/types";

const SLOT_COUNT = 3;

export default function ComparePage() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [selected, setSelected] = useState<(Player | null)[]>(Array(SLOT_COUNT).fill(null));
  const [queries, setQueries] = useState<string[]>(Array(SLOT_COUNT).fill(""));
  const [openSlot, setOpenSlot] = useState<number | null>(null);
  const [comparison, setComparison] = useState<PlayerComparisonResponse | null>(null);
  const [loadingPlayers, setLoadingPlayers] = useState(true);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [error, setError] = useState(false);
  const [comparisonError, setComparisonError] = useState(false);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);

  useEffect(() => {
    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        return state.recommendations_ready ? getPlayers({ limit: 1000, sort_by: "name" }) : [];
      })
      .then(setPlayers)
      .catch(() => setError(true))
      .finally(() => setLoadingPlayers(false));
  }, []);

  const selectedPlayers = useMemo(
    () => selected.filter((player): player is Player => Boolean(player?.element_id)),
    [selected],
  );
  const selectedIds = useMemo(
    () => selectedPlayers.map((player) => player.element_id as number),
    [selectedPlayers],
  );

  useEffect(() => {
    if (selectedIds.length < 2) {
      return;
    }

    let cancelled = false;
    comparePlayers(selectedIds)
      .then((data) => {
        if (!cancelled) setComparison(data);
      })
      .catch(() => {
        if (!cancelled) setComparisonError(true);
      })
      .finally(() => {
        if (!cancelled) setLoadingComparison(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedIds]);

  function choosePlayer(slot: number, player: Player) {
    setSelected((current) => current.map((item, index) => (index === slot ? player : item)));
    setQueries((current) => current.map((item, index) => (index === slot ? "" : item)));
    setComparison(null);
    setComparisonError(false);
    setLoadingComparison(true);
    setOpenSlot(null);
  }

  function clearPlayer(slot: number) {
    setSelected((current) => current.map((item, index) => (index === slot ? null : item)));
    setQueries((current) => current.map((item, index) => (index === slot ? "" : item)));
    setComparison(null);
    setComparisonError(false);
    setLoadingComparison(false);
    setOpenSlot(null);
  }

  if (loadingPlayers) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Compare Players" subtitle="Put up to three players side by side." />
        <TableSkeleton rows={5} />
      </div>
    );
  }

  if (seasonState && !seasonState.recommendations_ready) {
    return (
      <div className="space-y-5">
        <SectionHeader title="Compare Players" subtitle="Current comparisons are awaiting a validated refresh" />
        <DecisionStatusNotice seasonState={seasonState} />
      </div>
    );
  }

  if (error) return <ErrorState />;

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Compare Players"
        subtitle="A focused view for weighing price, floor, upside, and the next five fixtures."
      />

      <Panel className="overflow-visible">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[15px] font-semibold text-primary">
              <Scale className="h-4 w-4 text-fpl-green" />
              Choose players
            </div>
            <p className="mt-1 text-xs text-muted">Select at least two players to compare.</p>
          </div>
          <div className="rounded-full border border-fpl-border bg-fpl-raised px-3 py-1 text-xs text-secondary">
            {selectedPlayers.length} / 3 selected
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          {selected.map((player, slot) => (
            <PlayerSlot
              key={slot}
              slot={slot}
              player={player}
              query={queries[slot]}
              open={openSlot === slot}
              suggestions={suggestionsForSlot(players, selected, queries[slot], slot)}
              onQueryChange={(value) => {
                setQueries((current) => current.map((item, index) => (index === slot ? value : item)));
                setOpenSlot(slot);
              }}
              onFocus={() => setOpenSlot(slot)}
              onSelect={(choice) => choosePlayer(slot, choice)}
              onClear={() => clearPlayer(slot)}
              onClose={() => setOpenSlot(null)}
            />
          ))}
        </div>
      </Panel>

      {comparison && selectedIds.length >= 2 ? (
        <ComparisonPanel comparison={comparison} />
      ) : selectedIds.length >= 2 && loadingComparison ? (
        <TableSkeleton rows={6} />
      ) : selectedIds.length >= 2 && comparisonError ? (
        <div className="rounded-lg border border-fpl-red/30 bg-fpl-red/10 p-5 text-sm text-secondary">
          Could not load this comparison. Check that the API is running and try selecting the players again.
        </div>
      ) : (
        <div className="rounded-lg border border-fpl-border bg-fpl-card/70 p-8 text-center">
          <Scale className="mx-auto h-8 w-8 text-fpl-green" />
          <h2 className="mt-3 text-[15px] font-semibold text-primary">Your comparison will appear here</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted">
            Pick two or three players above to compare their price, form, expected points, defensive contributions,
            ownership, and fixture run.
          </p>
        </div>
      )}
    </div>
  );
}

function PlayerSlot({
  slot,
  player,
  query,
  open,
  suggestions,
  onQueryChange,
  onFocus,
  onSelect,
  onClear,
  onClose,
}: {
  slot: number;
  player: Player | null;
  query: string;
  open: boolean;
  suggestions: Player[];
  onQueryChange: (value: string) => void;
  onFocus: () => void;
  onSelect: (player: Player) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  const slotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (!slotRef.current?.contains(event.target as Node)) onClose();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  return (
    <div ref={slotRef} className="relative min-h-[88px] rounded-lg border border-fpl-border bg-fpl-raised p-3">
      <div className="mb-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
        Player {slot + 1}
        {player ? (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1 text-[10px] font-semibold normal-case tracking-normal text-secondary hover:text-primary"
          >
            <X className="h-3 w-3" />
            Change
          </button>
        ) : null}
      </div>
      {player ? (
        <div className="flex items-center gap-3">
          <img
            src={kitUrl(player.team_code, player.team, player.name)}
            alt={`${displayTeam(player.team, player.name)} kit`}
            className="h-10 w-10 object-contain"
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-primary">
              {displayPlayerName(player.name, player.web_name)}
            </div>
            <div className="mt-0.5 text-xs text-muted">
              {displayTeamShort(player.team, player.name)} - {positionCode(player.position)}
            </div>
          </div>
        </div>
      ) : (
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onFocus={onFocus}
            placeholder="Search player..."
            className="h-10 w-full rounded-lg border border-fpl-border bg-fpl-card px-3 pl-9 text-sm text-primary outline-none placeholder:text-muted focus:border-fpl-green"
          />
          {open && suggestions.length ? (
            <div className="absolute left-0 right-0 top-[72px] z-20 overflow-hidden rounded-lg border border-fpl-border bg-[#101514] shadow-[0_18px_36px_rgba(0,0,0,0.45)]">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.element_id}
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onSelect(suggestion)}
                  className="flex w-full items-center gap-3 border-b border-fpl-border/60 px-3 py-2.5 text-left last:border-0 hover:bg-white/[0.05]"
                >
                  <img
                    src={kitUrl(suggestion.team_code, suggestion.team, suggestion.name)}
                    alt=""
                    className="h-8 w-8 object-contain"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-primary">
                      {displayPlayerName(suggestion.name, suggestion.web_name)}
                    </span>
                    <span className="block text-xs text-muted">
                      {displayTeamShort(suggestion.team, suggestion.name)} - {positionCode(suggestion.position)} - £
                      {suggestion.price.toFixed(1)}m
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function ComparisonPanel({ comparison }: { comparison: PlayerComparisonResponse }) {
  const players = comparison.players;
  const transition = comparison.season_state !== "in_season";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-muted">
        <span className="rounded-full border border-fpl-border bg-fpl-raised px-2.5 py-1">
          {comparison.fixture_source}
        </span>
        <span className="rounded-full border border-fpl-border bg-fpl-raised px-2.5 py-1">
          {comparison.fixture_season}
        </span>
        <span className="rounded-full border border-fpl-amber/30 bg-fpl-amber/10 px-2.5 py-1 text-fpl-amber">
          {comparison.difficulty_source}
        </span>
      </div>

      {transition ? (
        <div className="flex items-start gap-3 rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 p-4 text-sm text-secondary">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-fpl-amber" />
          <div>
            <div className="font-semibold text-primary">Season transition</div>
            <p className="mt-1 leading-6">
              Prices, historical PPG, ownership, defensive contributions, and fixtures remain available. Live form,
              expected points, and start likelihood will appear once the new FPL season starts.
            </p>
          </div>
        </div>
      ) : null}

      <Panel title="Player comparison" className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] table-fixed">
            <thead>
              <tr className="border-b border-fpl-border bg-fpl-raised/60">
                <th className="w-[180px] px-5 py-4 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-muted">
                  Metric
                </th>
                {players.map((player) => (
                  <th key={player.element_id} className="px-4 py-4 text-left align-top">
                    <div className="flex items-center gap-3">
                      <img
                        src={kitUrl(player.team_code, player.team, player.name)}
                        alt={`${displayTeam(player.team, player.name)} kit`}
                        className="h-14 w-14 shrink-0 object-contain"
                      />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-primary">
                          {displayPlayerName(player.name, player.web_name)}
                        </div>
                        <div className="mt-1 text-xs text-muted">
                          {displayTeam(player.team, player.name)} - {positionCode(player.position)}
                        </div>
                      </div>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <ComparisonRow label="Current price" values={players.map((player) => player.price)} format={formatPrice} />
              <ComparisonRow
                label="Points per game"
                hint={transition ? "Historical season snapshot" : undefined}
                values={players.map((player) => player.points_per_game)}
                format={formatNumber}
                higherIsBetter
              />
              <ComparisonRow
                label="Form rating"
                values={players.map((player) => player.form)}
                format={formatNumber}
                higherIsBetter
                unavailable={transition}
              />
              <ComparisonRow
                label="Expected points (xP)"
                values={players.map((player) => player.expected_points)}
                format={formatNumber}
                higherIsBetter
                unavailable={transition}
              />
              <ComparisonRow
                label="Captain rank (0–1)"
                values={players.map((player) => player.captain_rank_score)}
                format={formatNumber}
                higherIsBetter
                unavailable={transition}
              />
              <ComparisonRow
                label="Start likelihood"
                values={players.map((player) => player.minutes_security)}
                format={formatPercent}
                higherIsBetter
                unavailable={transition}
              />
              <FixtureComparisonRow players={players} />
              <ComparisonRow
                label="DefCon / 90"
                hint="Defensive contributions per 90"
                values={players.map((player) => player.defensive_contribution_per_90)}
                format={formatNumber}
                higherIsBetter
              />
              <ComparisonRow
                label="Ownership"
                values={players.map((player) => player.selected_by_percent)}
                format={formatPercent}
                higherIsBetter
              />
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function ComparisonRow({
  label,
  hint,
  values,
  format,
  higherIsBetter = false,
  unavailable = false,
}: {
  label: string;
  hint?: string;
  values: (number | null)[];
  format: (value: number) => string;
  higherIsBetter?: boolean;
  unavailable?: boolean;
}) {
  const best = bestIndexes(values, higherIsBetter);
  return (
    <tr className="border-b border-fpl-border/70 last:border-0">
      <th className="px-5 py-4 text-left align-middle">
        <div className="text-sm font-semibold text-primary">{label}</div>
        {hint ? <div className="mt-1 text-[11px] font-normal text-muted">{hint}</div> : null}
      </th>
      {values.map((value, index) => (
        <td
          key={index}
          className={`px-4 py-4 align-middle font-mono text-sm ${
            value !== null && best.includes(index) ? "bg-fpl-green/10 text-fpl-green" : "text-secondary"
          }`}
        >
          {value === null || unavailable ? (
            <span className="font-sans text-xs leading-5 text-muted">Unavailable until season starts</span>
          ) : (
            format(value)
          )}
        </td>
      ))}
    </tr>
  );
}

function FixtureComparisonRow({ players }: { players: ComparisonPlayer[] }) {
  const averages = players.map((player) => player.average_fixture_difficulty);
  const best = bestIndexes(averages, false);
  return (
    <tr className="border-b border-fpl-border/70">
      <th className="px-5 py-4 text-left align-middle">
        <div className="text-sm font-semibold text-primary">Next 5 fixtures</div>
        <div className="mt-1 text-[11px] font-normal text-muted">Lower average is easier</div>
      </th>
      {players.map((player, index) => (
        <td
          key={player.element_id}
          className={`px-4 py-4 align-middle ${best.includes(index) ? "bg-fpl-green/10" : ""}`}
        >
          <div className="flex flex-wrap gap-1.5">
            {player.fixtures.length ? (
              player.fixtures.map((fixture, fixtureIndex) => (
                <FixtureChip
                  key={`${player.element_id}-${fixture.gw}-${fixtureIndex}`}
                  difficulty={fixture.difficulty}
                  opponentShortName={fixture.opponent}
                />
              ))
            ) : (
              <span className="text-xs text-muted">No fixtures available</span>
            )}
          </div>
          <div className={`mt-2 font-mono text-sm ${best.includes(index) ? "text-fpl-green" : "text-secondary"}`}>
            {player.average_fixture_difficulty === null ? "-" : player.average_fixture_difficulty.toFixed(2)} average
          </div>
        </td>
      ))}
    </tr>
  );
}

function suggestionsForSlot(
  players: Player[],
  selected: (Player | null)[],
  query: string,
  slot: number,
): Player[] {
  return players
    .filter((player) => player.element_id != null)
    .filter((player) => !selected.some((item, index) => index !== slot && item?.element_id === player.element_id))
    .filter((player) => matchesPlayerSearch(query, player.name, player.web_name, player.team))
    .slice(0, 7);
}

function bestIndexes(values: (number | null)[], higherIsBetter: boolean): number[] {
  const available = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (!available.length) return [];
  const best = higherIsBetter ? Math.max(...available) : Math.min(...available);
  return values.reduce<number[]>((indexes, value, index) => {
    if (value !== null && Math.abs(value - best) < 0.001) indexes.push(index);
    return indexes;
  }, []);
}

function formatPrice(value: number): string {
  return `£${value.toFixed(1)}m`;
}

function formatNumber(value: number): string {
  return value.toFixed(1);
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}
