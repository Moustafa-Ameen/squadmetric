"use client";

import { AlertTriangle, CalendarClock, CheckCircle2, ChevronDown, Repeat2, RotateCcw, Shield, Sparkles, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getChipStatuses, getChipTips } from "@/lib/api";
import type { ChipAvailabilityStatus, ChipStatusRow, ChipTipsResponse } from "@/lib/types";

type ChipCard = {
  key: string;
  name: string;
  subtitle: string;
  icon: LucideIcon;
  tip: string;
  status?: ChipAvailabilityStatus;
  usedGameweek?: number | null;
  availableFrom?: number | null;
};

const fallbackChips: ChipCard[] = [
  {
    key: "wc1",
    name: "Wildcard 1",
    subtitle: "first half",
    icon: RotateCcw,
    tip: "Best for an early rebuild when fixtures or injuries break your squad.",
  },
  {
    key: "wc2",
    name: "Wildcard 2",
    subtitle: "second half",
    icon: RotateCcw,
    tip: "Usually strongest before a major double gameweek or late-season fixture swing.",
  },
  {
    key: "fh1",
    name: "Free Hit 1",
    subtitle: "first half · unavailable GW1",
    icon: Zap,
    tip: "Save for a blank gameweek when many clubs do not play.",
  },
  {
    key: "bb1",
    name: "Bench Boost 1",
    subtitle: "first half · bench scores too",
    icon: Shield,
    tip: "Only powerful when all 15 squad members are expected to play.",
  },
  {
    key: "tc1",
    name: "Triple Captain 1",
    subtitle: "first half · captain scores 3×",
    icon: Sparkles,
    tip: "Best on a premium double-gameweek captain with strong minutes.",
  },
  {
    key: "fh2",
    name: "Free Hit 2",
    subtitle: "second half · one Gameweek only",
    icon: Zap,
    tip: "Preserve for the strongest blank or double-gameweek opportunity.",
  },
  {
    key: "bb2",
    name: "Bench Boost 2",
    subtitle: "second half · bench scores too",
    icon: Shield,
    tip: "Plan all 15 players around a strong double gameweek.",
  },
  {
    key: "tc2",
    name: "Triple Captain 2",
    subtitle: "second half · captain scores 3×",
    icon: Sparkles,
    tip: "Prefer a high-minutes premium captain with two strong fixtures.",
  },
];

const expandable = [
  {
    name: "Wildcard",
    best: "Early in the season (WC1) or before DGW (WC2).",
    paired: "Bench Boost planning, double gameweek fixture swings",
    body:
      "Use when your squad is fundamentally broken — injuries, price falls, or a fixture swing that affects 4+ players. Ideally time it before a run of easy fixtures or before a double gameweek to maximise the rebuilt squad's value.",
  },
  {
    name: "Free Hit",
    best: "The biggest blank gameweek of the season.",
    paired: "Blank gameweek planning",
    body:
      "Save for a blank gameweek when 6+ teams don't play. You temporarily build a squad from the playing teams only, then your original squad returns. It's wasted on a normal week.",
  },
  {
    name: "Bench Boost",
    best: "A double gameweek where your bench plays twice.",
    paired: "Wildcard setup, double gameweek fixture runs",
    body:
      "Only powerful if your bench has strong players with double fixtures. Check your bench's upcoming fixtures before using. A bench of squad fillers on a double GW will still disappoint.",
  },
  {
    name: "Triple Captain",
    best: "Double gameweek, premium player, easy opponents.",
    paired: "Premium captaincy picks, fixture ticker",
    body:
      "Triple your captain's points. Best used on a premium player with a double gameweek fixture. Haaland or Salah with two home games is the dream scenario.",
  },
];

const timeline = [
  "First WC, FH, BB and TC expire at the GW19 deadline",
  "Second set activates for the second half",
  "Only one chip can be used in a Gameweek",
  "A GW19 Free Hit prevents using the second Free Hit in GW20",
];

const chipCopy = {
  wildcard: "Best for an early rebuild when fixtures or injuries break your squad.",
  freehit: "Save for a blank gameweek when many clubs do not play.",
  bboost: "Only powerful when all 15 squad members are expected to play.",
  "3xc": "Best on a premium double-gameweek captain with strong minutes.",
};

function iconForChip(chipType: string): LucideIcon {
  if (chipType === "freehit") return Zap;
  if (chipType === "bboost") return Shield;
  if (chipType === "3xc") return Sparkles;
  return RotateCcw;
}

function liveChipCard(chip: ChipStatusRow): ChipCard {
  return {
    key: chip.key,
    name: chip.name,
    subtitle: chip.subtitle,
    icon: iconForChip(chip.chip_type),
    tip: chipCopy[chip.chip_type as keyof typeof chipCopy] ?? "Use this chip when the fixture context supports it.",
    status: chip.status,
    usedGameweek: chip.used_gameweek,
    availableFrom: chip.available_from,
  };
}

function chipStatusLabel(chip: ChipCard): string {
  if (chip.status === "used") return `Used (GW ${chip.usedGameweek})`;
  if (chip.status === "available") return "Available";
  if (chip.status === "not_yet_available") return `Available from GW ${chip.availableFrom}`;
  if (chip.status === "expired") return "Window closed";
  return "Unknown — connect your team to see chip availability";
}

export default function ChipsPage() {
  const [openChip, setOpenChip] = useState("Wildcard");
  const [chipTips, setChipTips] = useState<ChipTipsResponse | null>(null);
  const [chipStatus, setChipStatus] = useState<{
    status: "no_team" | "unavailable" | "ready";
    message: string;
    chips: ChipStatusRow[];
  } | null>(null);

  useEffect(() => {
    let active = true;
    const teamId = window.localStorage.getItem("fpl_team_id") || undefined;
    getChipTips(teamId)
      .then((response) => {
        if (active) setChipTips(response);
      })
      .catch(() => {
        if (active) {
          setChipTips({
            status: "unavailable",
            message: "AI chip tips are temporarily unavailable. Try again shortly.",
            alerts: [],
          });
        }
      });
    getChipStatuses(teamId)
      .then((response) => {
        if (active) setChipStatus(response);
      })
      .catch(() => {
        if (active) {
          setChipStatus({
            status: "unavailable",
            message: "Live chip availability is temporarily unavailable. Try again shortly.",
            chips: [],
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const teamConnected = Boolean(
    (chipStatus && chipStatus.status !== "no_team") ||
      (chipTips && chipTips.status !== "no_team"),
  );
  const liveChips = chipStatus?.status === "ready" ? chipStatus.chips.map(liveChipCard) : [];
  const chipCards = liveChips.length ? liveChips : fallbackChips;

  return (
    <div className="space-y-6">
      <SectionHeader
        title="When should I use my chips?"
        subtitle="A calm chip strategy guide for wildcard, free hit, bench boost, and triple captain decisions."
      />

      <Panel>
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-fpl-gold/30 bg-fpl-gold/10 text-fpl-gold">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-fpl-gold">AI Tip</div>
            <h2 className="mt-1 text-[18px] font-semibold text-primary">Personalized chip timing</h2>
            <p className="mt-1 text-[13px] text-secondary">
              Recommendations come from the same point-in-time chip and transfer engine used by the benchmark.
            </p>
          </div>
        </div>
        {!chipTips ? (
          <div className="rounded-lg border border-fpl-border bg-[#161616] p-4 text-sm text-secondary">
            Checking your squad projections...
          </div>
        ) : chipTips.status === "no_team" ? (
          <div className="rounded-lg border border-fpl-border bg-[#161616] p-4 text-sm text-secondary">
            Connect your FPL team to receive chip timing tips based on your own squad.
          </div>
        ) : chipTips.status === "unavailable" ? (
          <div className="flex items-start gap-3 rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 p-4 text-sm text-secondary">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-fpl-amber" />
            <div>{chipTips.message}</div>
          </div>
        ) : chipTips.status === "insufficient_data" ? (
          <div className="rounded-lg border border-fpl-border bg-[#161616] p-4 text-sm text-secondary">
            {chipTips.message}
          </div>
        ) : (
          <>
            {chipTips.recommendation ? (
              <div className="rounded-lg border border-fpl-green/30 bg-fpl-green/[0.05] p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.14em] text-fpl-green">
                      Optimizer recommendation · GW{chipTips.recommendation.gameweek}
                    </div>
                    <h3 className="mt-1 text-xl font-semibold text-primary">
                      {chipTips.recommendation.action === "use"
                        ? `Use ${chipTips.recommendation.chip}`
                        : "Save your chips"}
                    </h3>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">
                      {chipTips.recommendation.reason}
                    </p>
                  </div>
                  <div className="rounded-lg border border-fpl-green/25 bg-fpl-green/10 px-4 py-3 text-right">
                    <div className="font-mono text-2xl font-semibold text-fpl-green">
                      {chipTips.recommendation.expected_horizon_gain > 0 ? "+" : ""}
                      {chipTips.recommendation.expected_horizon_gain.toFixed(2)}
                    </div>
                    <div className="text-[10px] uppercase tracking-[0.12em] text-muted">horizon points</div>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded border border-fpl-border bg-[#161616] p-3">
                    <div className="text-xs text-muted">Immediate gain</div>
                    <div className="mt-1 font-mono text-primary">{chipTips.recommendation.expected_immediate_gain.toFixed(2)}</div>
                  </div>
                  <div className="rounded border border-fpl-border bg-[#161616] p-3">
                    <div className="text-xs text-muted">Downside range</div>
                    <div className="mt-1 font-mono text-primary">
                      {chipTips.recommendation.downside_range.low.toFixed(1)}–{chipTips.recommendation.downside_range.high.toFixed(1)}
                    </div>
                  </div>
                  <div className="rounded border border-fpl-border bg-[#161616] p-3">
                    <div className="text-xs text-muted">Confidence</div>
                    <div className="mt-1 capitalize text-primary">{chipTips.recommendation.confidence}</div>
                  </div>
                  <div className="rounded border border-fpl-border bg-[#161616] p-3">
                    <div className="text-xs text-muted">Transfer interaction</div>
                    <div className="mt-1 text-primary">
                      {chipTips.recommendation.ordinary_transfer_applied ? "Transfer included" : "No transfer"}
                    </div>
                  </div>
                </div>
                {chipTips.recommendation.best_alternative ? (
                  <div className="mt-4 text-xs text-secondary">
                    Best projected alternative: use {chipTips.recommendation.best_alternative.chip} in GW
                    {chipTips.recommendation.best_alternative.gameweek} for +
                    {chipTips.recommendation.best_alternative.expected_horizon_gain.toFixed(2)} horizon points.
                  </div>
                ) : null}
              </div>
            ) : null}
            {chipTips.alerts.length ? (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {chipTips.alerts.map((alert) => (
                  <div key={alert.key} className="rounded-lg border border-fpl-gold/35 bg-fpl-gold/[0.05] p-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-fpl-gold">Explanatory squad signal · {alert.chip}</div>
                    <p className="mt-2 text-sm leading-6 text-primary">{alert.message}</p>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-4 text-xs text-muted">
              {chipTips.model} · {chipTips.model_version} · data cutoff {chipTips.data_cutoff ?? "live"}
            </div>
          </>
        )}
      </Panel>

      <Panel>
        <div className="mb-4">
          <h2 className="text-[18px] font-semibold text-primary">Your chip status</h2>
          <p className="mt-1 text-[13px] text-secondary">
            {chipStatus?.status === "ready"
              ? `${chipStatus.message} Window dates are read from the current FPL game configuration.`
              : chipStatus?.status === "unavailable"
                ? chipStatus.message
                : teamConnected
                  ? "Live chip availability is temporarily unavailable."
                  : "Connect your FPL team to see which chips you have used and which remain available."}
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {chipCards.map((chip) => {
            const Icon = chip.icon;
            const liveStatus = Boolean(chip.status);
            const statusClass =
              chip.status === "available"
                ? "border-fpl-green/30 bg-fpl-green/10 text-fpl-green"
                : chip.status === "not_yet_available"
                  ? "border-fpl-amber/30 bg-fpl-amber/10 text-fpl-amber"
                  : "border-fpl-border bg-fpl-raised text-muted";
            return (
              <div key={chip.key} className="rounded-lg border border-fpl-border bg-[#161616] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-primary">{chip.name}</div>
                    <div className="mt-1 text-xs text-muted">{chip.subtitle}</div>
                  </div>
                  <Icon className="h-5 w-5 text-fpl-green" />
                </div>
                <div className={`mt-4 flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] ${liveStatus ? statusClass : "border-fpl-border bg-fpl-raised text-muted"}`}>
                  {chip.status === "used" ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
                  {chip.status ? chipStatusLabel(chip) : chipStatus ? (chipStatus.status === "unavailable" ? "Live status unavailable" : chipStatusLabel(chip)) : "Checking live status..."}
                </div>
                <p className="mt-3 text-xs leading-5 text-secondary">{chip.tip}</p>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <div className="mb-4">
          <h2 className="text-[18px] font-semibold text-primary">When to use each chip</h2>
          <p className="mt-1 text-[13px] text-secondary">Click a chip to expand the expert timing note.</p>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          {expandable.map((chip) => {
            const isOpen = chip.name === openChip;
            return (
              <button
                type="button"
                key={chip.name}
                onClick={() => setOpenChip(isOpen ? "" : chip.name)}
                className={`rounded-lg border p-4 text-left transition ${
                  isOpen ? "border-fpl-green bg-fpl-green/[0.06]" : "border-fpl-border bg-[#161616] hover:border-fpl-green/40"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-primary">{chip.name}</div>
                  <ChevronDown className={`h-4 w-4 text-muted transition ${isOpen ? "rotate-180" : ""}`} />
                </div>
                {isOpen ? (
                  <div className="mt-4 space-y-3 text-sm leading-6 text-secondary">
                    <p>{chip.body}</p>
                    <div className="rounded-lg border border-fpl-border bg-black/20 p-3">
                      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-fpl-green">
                        <CalendarClock className="h-4 w-4" />
                        Best timing
                      </div>
                      <div className="mt-2 text-primary">{chip.best}</div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <Repeat2 className="h-4 w-4 text-fpl-gold" />
                      Commonly paired with: {chip.paired}
                    </div>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted">{chip.best}</p>
                )}
              </button>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <div className="mb-5">
          <h2 className="text-[18px] font-semibold text-primary">Classic chip strategy timeline</h2>
          <p className="mt-1 text-[13px] text-secondary">A rough sequence many experienced FPL managers plan around.</p>
        </div>
        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-[760px] items-center">
            {timeline.map((item, index) => (
              <div key={item} className="flex flex-1 items-center">
                <div className="flex flex-col items-center gap-2">
                  <div className="flex h-11 w-11 items-center justify-center rounded-full border border-fpl-green/40 bg-fpl-green/10 text-fpl-green">
                    <CheckCircle2 className="h-5 w-5" />
                  </div>
                  <div className="max-w-[120px] text-center text-xs font-semibold text-primary">{item}</div>
                </div>
                {index < timeline.length - 1 ? <div className="mx-3 h-px flex-1 bg-fpl-border" /> : null}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-5 rounded-lg border border-fpl-gold/30 bg-fpl-gold/[0.04] p-4 text-sm text-secondary">
          This is a rough guide. Fixtures and your squad situation should always drive the final call.
        </div>
      </Panel>
    </div>
  );
}
