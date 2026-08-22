"use client";

import type { SquadPlayer } from "@/lib/types";
import { points } from "@/lib/format";
import { useDrawer } from "@/context/DrawerContext";

interface PitchCardProps {
  player: SquadPlayer;
  average: number;
  bench?: boolean;
}

export function PitchCard({ player, average, bench = false }: PitchCardProps) {
  const { openDrawer } = useDrawer();
  const predicted = player.expected_points ?? 0;
  const color = predicted >= average ? "text-fpl-green" : "text-fpl-red";
  const dotColor = startDotColor(player.start_likelihood);
  const teamCode = player.team_code ?? 1;
  const width = bench ? "w-[112px]" : "w-[110px]";
  const kitSize = bench ? "h-14 w-[68px]" : "h-[60px] w-[70px]";

  return (
    <button
      type="button"
      onClick={() => openDrawer(player.name)}
      className={`fpl-pitch-card relative flex ${width} flex-col items-center rounded-lg p-2 text-center hover:bg-white/10 ${
        bench ? "opacity-70" : ""
      }`}
    >
      <div className="relative">
        <img
          src={`https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCode}-66.png`}
          alt={`${player.team} kit`}
          className={`${kitSize} object-contain`}
        />
        {player.is_captain || player.is_vice_captain ? (
          <span
            className={`absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
              player.is_captain ? "bg-fpl-gold text-fpl-dark" : "bg-slate-300 text-fpl-dark"
            }`}
          >
            {player.is_captain ? "C" : "V"}
          </span>
        ) : null}
      </div>
      <div className="mt-1 w-full truncate text-[13px] font-semibold text-white">
        {player.web_name ?? player.name.split(" ").at(-1)}
      </div>
      <div className={`font-mono text-xs font-bold ${color}`}>{points(predicted)} xP</div>
      <span className={`mt-1 h-2 w-2 rounded-full ${dotColor}`} aria-label="Start likelihood" />
    </button>
  );
}

function startDotColor(value: number | null | undefined) {
  const safe = value ?? 0;
  if (safe >= 0.8) return "bg-fpl-green";
  if (safe >= 0.5) return "bg-fpl-amber";
  return "bg-fpl-red";
}
