"use client";

import { ShieldCheck } from "lucide-react";
import { positionCode, points, price } from "@/lib/format";

export type VisualSquadPlayer = {
  id: number | string;
  name: string;
  shortName?: string | null;
  team: string;
  teamCode?: number | null;
  position: string;
  expectedPoints?: number | null;
  startLikelihood?: number | null;
  playerPrice?: number | null;
  starter: boolean;
  benchOrder?: number | null;
  captain?: boolean;
  viceCaptain?: boolean;
};

export function SquadPitch({ players, title = "Recommended XI", showBench = true }: { players: VisualSquadPlayer[]; title?: string; showBench?: boolean }) {
  const starters = players.filter((player) => player.starter);
  const bench = players
    .filter((player) => !player.starter)
    .sort((a, b) => (a.benchOrder ?? 99) - (b.benchOrder ?? 99));
  const outfieldBenchOrder = new Map(
    bench
      .filter((player) => positionCode(player.position) !== "GK")
      .map((player, index) => [player.id, index + 1]),
  );
  const rows = ["GK", "DEF", "MID", "FWD"].map((position) =>
    starters.filter((player) => positionCode(player.position) === position),
  );

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_16px_44px_rgba(15,23,42,0.08)]" aria-label={title}>
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="text-base font-extrabold text-slate-950">{title}</h2>
          <p className="mt-0.5 text-xs text-slate-500">Captain, vice-captain and bench order are shown on the pitch.</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
          <ShieldCheck className="h-3.5 w-3.5" /> Legal XI
        </span>
      </div>

      <div className="relative overflow-hidden bg-[linear-gradient(180deg,#138a55_0%,#087142_52%,#0a804b_100%)] px-2 py-5 sm:px-5">
        <PitchMarkings />
        <div className="relative z-10 space-y-5 sm:space-y-6">
          {rows.map((row, index) => (
            <div key={index} className="flex min-h-[88px] items-center justify-center gap-1.5 sm:gap-4">
              {row.map((player) => <PitchPlayer key={player.id} player={player} />)}
            </div>
          ))}
        </div>
      </div>

      {showBench ? (
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-4 sm:px-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-extrabold uppercase tracking-[0.14em] text-slate-500">Substitutes</div>
            <div className="text-xs text-slate-500">Order matters for autosubs</div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {bench.map((player) => <BenchPlayer key={player.id} player={player} order={outfieldBenchOrder.get(player.id) ?? 0} />)}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PitchMarkings() {
  return <div aria-hidden="true" className="pointer-events-none absolute inset-4 rounded-2xl border border-white/20"><div className="absolute left-1/2 top-1/2 h-28 w-28 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20" /><div className="absolute left-0 right-0 top-1/2 border-t border-white/20" /><div className="absolute left-1/2 top-0 h-16 w-40 -translate-x-1/2 border-x border-b border-white/20" /><div className="absolute bottom-0 left-1/2 h-16 w-40 -translate-x-1/2 border-x border-t border-white/20" /></div>;
}

function PitchPlayer({ player }: { player: VisualSquadPlayer }) {
  return (
    <div className="relative flex w-[66px] flex-col items-center text-center sm:w-[104px]">
      <div className="relative flex h-10 w-12 items-center justify-center sm:h-12 sm:w-14">
        <TeamKit player={player} className="max-h-full max-w-full object-contain drop-shadow-md" />
        {player.captain || player.viceCaptain ? <span className={`absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-black shadow ${player.captain ? "bg-amber-300 text-slate-950" : "bg-white text-violet-700"}`}>{player.captain ? "C" : "V"}</span> : null}
      </div>
      <div className="mt-1 w-full truncate rounded-t-md bg-white px-1.5 py-1 text-[10px] font-extrabold text-slate-950 shadow sm:text-xs">{label(player)}</div>
      <div className="w-full rounded-b-md bg-slate-950/90 px-1 py-0.5 text-[9px] font-bold text-white sm:text-[10px]">{points(player.expectedPoints)} xP</div>
    </div>
  );
}

function BenchPlayer({ player, order }: { player: VisualSquadPlayer; order: number }) {
  return <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-2.5"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-extrabold text-slate-600">{positionCode(player.position) === "GK" ? "GK" : order}</span><TeamKit player={player} className="h-8 w-8 object-contain" /><div className="min-w-0"><div className="truncate text-xs font-extrabold text-slate-900">{label(player)}</div><div className="mt-0.5 text-[10px] text-slate-500">{player.playerPrice == null ? player.team : `${price(player.playerPrice)} · ${points(player.expectedPoints)} xP`}</div></div></div>;
}

function label(player: VisualSquadPlayer) {
  return player.shortName || player.name.split(" ").at(-1) || player.name;
}

function TeamKit({ player, className }: { player: VisualSquadPlayer; className: string }) {
  if (player.teamCode) return <img src={`https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${player.teamCode}-66.png`} alt="" className={className} />;
  return <span aria-hidden="true" className={`flex items-center justify-center rounded-md bg-violet-200 text-[9px] font-black text-violet-950 ${className}`}>{player.team.slice(0, 3).toUpperCase()}</span>;
}
