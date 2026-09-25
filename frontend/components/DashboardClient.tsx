"use client";

import Link from "next/link";
import { ArrowRight, Check, CircleAlert, Clock3, Coins, Info, RefreshCw, Repeat2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useDrawer } from "@/context/DrawerContext";
import type { DecisionCenterPlayer, DecisionCenterResponse, OverviewResponse, SeasonState, TeamRatingFactor } from "@/lib/types";
import { SquadPitch, type VisualSquadPlayer } from "./SquadPitch";

export function DashboardClient({ overview, seasonState, seasonStateUnavailable, decisionCenter, teamId }: { overview: OverviewResponse; seasonState: SeasonState | null; seasonStateUnavailable: boolean; decisionCenter: DecisionCenterResponse | null; teamId: string }) {
  const { openDrawer } = useDrawer();
  const [lineupView, setLineupView] = useState<"current" | "recommended">("current");
  const rating = decisionCenter?.rating;
  const recommendation = decisionCenter?.status === "ready" ? decisionCenter.recommendation : undefined;
  const gameweek = decisionCenter?.gameweek ?? seasonState?.next_gw ?? seasonState?.current_gw ?? 1;
  if (!rating) return <EmptyRating teamId={teamId} message={decisionCenter?.message} gameweek={gameweek} />;

  const firstTransfer = recommendation?.transfers[0];
  const current = decisionCenter?.current_lineup;
  const selectedLineup = lineupView === "current" && current ? current : recommendation;
  const pitchPlayers = selectedLineup
    ? visualPlayers(selectedLineup.starting_xi, selectedLineup.bench_order, selectedLineup.captain_id, selectedLineup.vice_captain_id)
    : [];
  const changed = rating.after_grade !== rating.grade;
  const bank = decisionCenter?.state_before?.bank;
  const freeTransfers = decisionCenter?.state_before?.free_transfers;

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-xs font-black uppercase tracking-[0.16em] text-violet-700">Gameweek {gameweek}</div>
          <h1 className="mt-2 text-3xl font-black tracking-[-0.045em] text-slate-950 sm:text-4xl">My Team</h1>
          <p className="mt-2 text-sm text-slate-600">Your squad quality, key account details, and clearest improvement.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={"rounded-full px-3 py-2 text-xs font-bold " + (rating.provisional ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800")}>{rating.provisional ? "Provisional screenshot" : "Team #" + teamId + " linked"}</span>
          <Link href="/onboarding" className="sm-secondary-button px-3 py-2 text-xs">Change team</Link>
        </div>
      </header>

      {seasonStateUnavailable ? <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status"><strong>Freshness check unavailable.</strong> Confirm the deadline before acting.</div> : null}
      {rating.provisional ? <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950"><Info className="mt-0.5 h-4 w-4 shrink-0" /><span>This grade uses current list prices. Add your Team ID for exact selling prices and transfer history.</span></div> : null}

      <section className="grid overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.10)] lg:grid-cols-[260px_minmax(0,1fr)_minmax(300px,0.72fr)]">
        <div className="flex flex-col items-center justify-center border-b border-slate-200 bg-slate-50/70 px-6 py-8 text-center lg:border-b-0 lg:border-r">
          <GradeCircle grade={rating.grade} />
          <div className="mt-5 text-xs font-black uppercase tracking-[0.14em] text-slate-500">Three-gameweek grade</div>
          <div className="mt-2 text-sm font-semibold text-slate-700">{rating.gap_to_best.toFixed(1)} points behind the best same-budget squad found</div>
        </div>
        <div className="border-b border-slate-200 p-6 sm:p-8 lg:border-b-0 lg:border-r">
          <div className="text-xs font-black uppercase tracking-[0.14em] text-violet-700">Squad assessment</div>
          <h2 className="mt-3 text-2xl font-black tracking-[-0.035em] text-slate-950">Your squad is {rating.grade}</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">{rating.summary}</p>
          <div className="mt-6 space-y-3">{rating.factors.map((factor) => <RatingFactor key={factor.label} factor={factor} />)}</div>
          <details className="mt-5 text-xs text-slate-500"><summary className="cursor-pointer font-bold text-slate-600">How the grade works</summary><p className="mt-2 max-w-xl leading-5">{rating.method}</p></details>
        </div>
        <div className="bg-gradient-to-br from-violet-50 to-white p-6 sm:p-8">
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-violet-700"><Sparkles className="h-4 w-4" />Best improvement</div>
          {firstTransfer ? <>
            <h2 className="mt-4 text-xl font-black tracking-[-0.025em] text-slate-950">{firstTransfer.outgoing_name} <span className="text-slate-400">→</span> {firstTransfer.incoming_name}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{recommendation?.transfer_count === 1 ? "One transfer" : String(recommendation?.transfer_count) + " linked transfers"} worth <strong className="text-emerald-700">+{recommendation?.gain_vs_no_action.toFixed(1)} projected points</strong> over three gameweeks{recommendation?.hit_cost ? " after a " + recommendation.hit_cost + "-point hit" : ""}.</p>
          </> : <>
            <h2 className="mt-4 text-xl font-black text-slate-950">Keep the free transfer</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">No legal move adds enough value right now. Keeping the transfer gives you more options next week.</p>
          </>}
          <div className="mt-6 flex items-center gap-3 rounded-2xl border border-violet-100 bg-white p-4"><GradeMini grade={rating.grade} label="Now" /><ArrowRight className="h-5 w-5 shrink-0 text-slate-300" /><GradeMini grade={rating.after_grade} label={changed ? "After move" : "Best action"} highlighted={changed} /></div>
          <Link href="/decisions" className="sm-primary-button mt-5 w-full justify-center px-4 py-3">View this week’s plan<ArrowRight className="h-4 w-4" /></Link>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <QuickFact icon={<Coins className="h-4 w-4" />} label="Bank" value={typeof bank === "number" ? "£" + bank.toFixed(1) + "m" : "—"} />
        <QuickFact icon={<Repeat2 className="h-4 w-4" />} label="Free transfers" value={typeof freeTransfers === "number" ? String(freeTransfers) : "—"} />
        <QuickFact icon={<Clock3 className="h-4 w-4" />} label="Deadline" value={formatDeadline(decisionCenter?.deadline)} />
      </section>

      {pitchPlayers.length ? <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-xl font-black text-slate-950">Your lineup</h2><p className="mt-1 text-sm text-slate-500">Select any player to view their details.</p></div>
          <div className="flex rounded-xl border border-slate-200 bg-slate-50 p-1"><LineupButton active={lineupView === "current"} onClick={() => setLineupView("current")}>Current XI</LineupButton><LineupButton active={lineupView === "recommended"} onClick={() => setLineupView("recommended")}>Best XI</LineupButton></div>
        </div>
        <SquadPitch players={pitchPlayers} title={(lineupView === "current" && current ? "Current GW" : "Best GW") + gameweek + " lineup"} onPlayerClick={(player) => openDrawer(player.name)} />
      </div> : null}
      <p className="text-center text-xs text-slate-500">{overview.player_count.toLocaleString()} players evaluated · projections are estimates, not guarantees</p>
    </div>
  );
}

function EmptyRating({ teamId, message, gameweek }: { teamId: string; message?: string; gameweek: number }) {
  return <div className="mx-auto max-w-3xl py-8"><div className="text-xs font-black uppercase tracking-[0.16em] text-violet-700">Gameweek {gameweek}</div><h1 className="mt-2 text-3xl font-black tracking-[-0.04em] text-slate-950 sm:text-4xl">Rate your FPL squad</h1><p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">Connect with a public Team ID for an exact grade, or upload a screenshot for a provisional one.</p><div className="mt-7 rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] sm:p-8"><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-700">{teamId ? <RefreshCw className="h-6 w-6" /> : <Sparkles className="h-6 w-6" />}</div><h2 className="mt-5 text-xl font-black text-slate-950">{teamId ? "Your grade is not ready yet" : "Connect your squad once"}</h2><p className="mt-2 text-sm leading-6 text-slate-600">{message || (teamId ? "Live projections could not produce a complete legal rating." : "No FPL password is needed. You stay in control of every recommendation.")}</p><Link href="/onboarding" className="sm-primary-button mt-6 justify-center px-5 py-3">{teamId ? "Retry team setup" : "Connect or upload screenshot"}<ArrowRight className="h-4 w-4" /></Link></div></div>;
}
function GradeCircle({ grade }: { grade: string }) { const colors = gradeColors(grade); return <div className={"flex h-44 w-44 items-center justify-center rounded-full border-[12px] shadow-[inset_0_0_0_5px_rgba(255,255,255,0.9),0_16px_35px_rgba(15,23,42,0.12)] " + colors.border + " " + colors.background}><div className={"text-6xl font-black tracking-[-0.08em] " + colors.text}>{grade}</div></div>; }
function GradeMini({ grade, label, highlighted = false }: { grade: string; label: string; highlighted?: boolean }) { const colors = gradeColors(grade); return <div className="flex flex-1 items-center gap-3"><span className={"flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-4 text-sm font-black " + colors.border + " " + colors.background + " " + colors.text}>{grade}</span><span className={"text-xs font-bold " + (highlighted ? "text-emerald-700" : "text-slate-600")}>{label}</span></div>; }
function RatingFactor({ factor }: { factor: TeamRatingFactor }) { const warning = factor.status === "warning"; return <div className="flex items-start gap-3"><span className={"mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full " + (warning ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700")}>{warning ? <CircleAlert className="h-3 w-3" /> : <Check className="h-3 w-3" />}</span><div><div className="text-sm font-bold text-slate-900">{factor.label}</div><div className="mt-0.5 text-xs leading-5 text-slate-500">{factor.detail}</div></div></div>; }
function QuickFact({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) { return <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-50 text-violet-700">{icon}</span><div><div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">{label}</div><div className="mt-0.5 text-sm font-black text-slate-950">{value}</div></div></div>; }
function LineupButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) { return <button type="button" onClick={onClick} aria-pressed={active} className={"rounded-lg px-4 py-2 text-xs font-bold transition " + (active ? "bg-white text-violet-700 shadow-sm" : "text-slate-500 hover:text-slate-900")}>{children}</button>; }
function visualPlayers(starters: DecisionCenterPlayer[], bench: DecisionCenterPlayer[], captainId: number | null, viceCaptainId: number | null): VisualSquadPlayer[] { return [...starters.map((player) => ({ ...visualPlayer(player), starter: true, captain: player.element_id === captainId, viceCaptain: player.element_id === viceCaptainId })), ...bench.map((player, index) => ({ ...visualPlayer(player), starter: false, benchOrder: index }))]; }
function visualPlayer(player: DecisionCenterPlayer) { return { id: player.element_id, name: player.name, shortName: player.web_name, team: player.team, teamCode: player.team_code, position: player.position, expectedPoints: player.expected_points, startLikelihood: player.start_likelihood, playerPrice: player.price }; }
function formatDeadline(value?: string | null) { if (!value) return "—"; return new Intl.DateTimeFormat("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function gradeColors(grade: string) { if (grade.startsWith("A")) return { border: "border-emerald-500", background: "bg-emerald-50", text: "text-emerald-700" }; if (grade.startsWith("B")) return { border: "border-lime-500", background: "bg-lime-50", text: "text-lime-700" }; if (grade.startsWith("C")) return { border: "border-amber-400", background: "bg-amber-50", text: "text-amber-700" }; if (grade === "D" || grade === "E") return { border: "border-orange-500", background: "bg-orange-50", text: "text-orange-700" }; return { border: "border-rose-500", background: "bg-rose-50", text: "text-rose-700" }; }
