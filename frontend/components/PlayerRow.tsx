"use client";

import type { Player } from "@/lib/types";
import { points, positionCode } from "@/lib/format";
import { useDrawer } from "@/context/DrawerContext";
import { StartLikelihood } from "./StartLikelihood";

interface PlayerRowProps {
  player: Player;
  compact?: boolean;
}

export function PlayerRow({ player, compact = false }: PlayerRowProps) {
  const { openDrawer } = useDrawer();
  const rowPadding = compact ? "py-1.5" : "py-3";

  return (
    <tr className="fpl-player-row border-b border-fpl-border/80 text-sm odd:bg-fpl-raised/40">
      <td className={`${rowPadding} pr-4 font-medium text-primary`}>
        <button type="button" onClick={() => openDrawer(player.name)} className="hover:text-fpl-green">
          {player.name}
        </button>
      </td>
      <td className={`${rowPadding} pr-4 text-secondary`}>{player.team}</td>
      <td className={`${rowPadding} pr-4 text-secondary`}>{positionCode(player.position)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.price)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.total_points, 0)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.ppg)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.form)}</td>
      <td className={`${rowPadding} pr-4`}>
        <StartLikelihood value={player.start_likelihood} />
      </td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.value)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.captain_rank_score)}</td>
      <td className={`${rowPadding} pr-4 font-mono text-primary`}>{points(player.transfer_rank_score)}</td>
    </tr>
  );
}
