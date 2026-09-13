"use client";

import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  RotateCcw,
  Shield,
  Sparkles,
  Target,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getChipOpportunities, getChipStatuses } from "@/lib/api";
import type {
  ChipAvailabilityStatus,
  ChipOpportunitiesResponse,
  ChipOpportunity,
  ChipStatusRow,
} from "@/lib/types";

type ChipCard = {
  key: string;
  name: string;
  subtitle: string;
  icon: LucideIcon;
  status?: ChipAvailabilityStatus;
  usedGameweek?: number | null;
  availableFrom?: number | null;
};

const fallbackChips: ChipCard[] = [
  { key: "wc1", name: "Wildcard 1", subtitle: "first half", icon: RotateCcw },
  { key: "fh1", name: "Free Hit 1", subtitle: "first half", icon: Zap },
  { key: "bb1", name: "Bench Boost 1", subtitle: "first half", icon: Shield },
  { key: "tc1", name: "Triple Captain 1", subtitle: "first half", icon: Sparkles },
  { key: "wc2", name: "Wildcard 2", subtitle: "second half", icon: RotateCcw },
  { key: "fh2", name: "Free Hit 2", subtitle: "second half", icon: Zap },
  { key: "bb2", name: "Bench Boost 2", subtitle: "second half", icon: Shield },
  { key: "tc2", name: "Triple Captain 2", subtitle: "second half", icon: Sparkles },
];

const methodology = [
  {
    name: "Triple Captain",
    icon: Sparkles,
    text: "An in-form, high-minutes attacker meeting a defence allowing strong expected-goal numbers, with doubles preferred.",
  },
  {
    name: "Bench Boost",
    icon: Shield,
    text: "A week where affordable squad-depth options combine strong fixtures with reliable projected starts.",
  },
  {
    name: "Free Hit",
    icon: Zap,
    text: "A published blank or double Gameweek where temporary fixture coverage has unusual league-wide value.",
  },
  {
    name: "Wildcard",
    icon: RotateCcw,
    text: "A five-Gameweek fixture swing shared by several teams, creating a useful window for a structural rebuild.",
  },
];

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
    status: chip.status,
    usedGameweek: chip.used_gameweek,
    availableFrom: chip.available_from,
  };
}

function chipStatusLabel(chip: ChipCard): string {
  if (chip.status === "used") return `Used in GW${chip.usedGameweek}`;
  if (chip.status === "available") return "Available";
  if (chip.status === "not_yet_available") return `Available from GW${chip.availableFrom}`;
  if (chip.status === "expired") return "Window closed";
  return "Connect your team for status";
}

function confidenceClass(confidence: ChipOpportunity["confidence"]): string {
  if (confidence === "high") return "border-fpl-green/35 bg-fpl-green/10 text-fpl-green";
  if (confidence === "medium") return "border-fpl-gold/35 bg-fpl-gold/10 text-fpl-gold";
  return "border-fpl-border bg-fpl-raised text-muted";
}

function alternativeLabel(opportunity: ChipOpportunity, index: number): string {
  const alternative = opportunity.alternatives[index];
  if (!alternative) return "";
  const gameweek = alternative.gameweek ? `GW${alternative.gameweek}` : "later window";
  if (alternative.player) return `${gameweek} · ${alternative.player}`;
  if (alternative.blank_teams?.length || alternative.double_teams?.length) {
    return `${gameweek} · ${alternative.blank_teams?.length ?? 0} blanks, ${alternative.double_teams?.length ?? 0} doubles`;
  }
  if (alternative.teams?.length) {
    return `${gameweek} · ${alternative.teams.slice(0, 3).map((team) => team.team).join(", ")}`;
  }
  return gameweek;
}

export default function ChipsPage() {
  const [opportunities, setOpportunities] = useState<ChipOpportunitiesResponse | null>(null);
  const [chipStatus, setChipStatus] = useState<{
    status: "no_team" | "unavailable" | "ready";
    message: string;
    chips: ChipStatusRow[];
  } | null>(null);

  useEffect(() => {
    let active = true;
    const teamId = window.localStorage.getItem("fpl_team_id") || undefined;
    getChipOpportunities()
      .then((response) => {
        if (active) setOpportunities(response);
      })
      .catch(() => {
        if (active) {
          setOpportunities({
            status: "unavailable",
            message: "Chip opportunities are temporarily unavailable.",
            opportunities: [],
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
            message: "Live chip availability is temporarily unavailable.",
            chips: [],
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const liveChips = chipStatus?.status === "ready" ? chipStatus.chips.map(liveChipCard) : [];
  const chipCards = liveChips.length ? liveChips : fallbackChips;

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Chip opportunity radar"
        subtitle="League-wide windows worth considering—never an instruction to spend your chip."
      />

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-fpl-gold/30 bg-fpl-gold/10 text-fpl-gold">
              <Target className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-fpl-gold">
                Public fixture intelligence
              </div>
              <h2 className="mt-1 text-[18px] font-semibold text-primary">
                Strongest currently visible opportunities
              </h2>
              <p className="mt-1 max-w-3xl text-[13px] leading-6 text-secondary">
                These cards use public fixtures, player form, expected involvement, defensive weakness and minutes confidence. They do not inspect your squad and cannot activate a chip.
              </p>
            </div>
          </div>
          {opportunities?.status === "ready" ? (
            <div className="rounded-full border border-fpl-border bg-fpl-raised px-3 py-1 text-xs text-muted">
              GW{opportunities.target_gameweek}–GW{opportunities.horizon_end_gameweek}
            </div>
          ) : null}
        </div>

        {!opportunities ? (
          <div className="mt-5 rounded-lg border border-fpl-border bg-[#161616] p-4 text-sm text-secondary">
            Ranking upcoming chip opportunities…
          </div>
        ) : opportunities.status === "unavailable" ? (
          <div className="mt-5 flex items-start gap-3 rounded-lg border border-fpl-amber/30 bg-fpl-amber/10 p-4 text-sm text-secondary">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-fpl-amber" />
            <div>{opportunities.message}</div>
          </div>
        ) : (
          <>
            <div className="mt-5 grid gap-4 xl:grid-cols-2">
              {opportunities.opportunities.map((opportunity) => {
                const Icon = iconForChip(opportunity.chip_type);
                return (
                  <article key={opportunity.chip_type} className="rounded-xl border border-fpl-border bg-[#161616] p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-fpl-green/25 bg-fpl-green/10 text-fpl-green">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.13em] text-muted">
                            {opportunity.chip}
                          </div>
                          <div className="mt-1 font-mono text-sm text-fpl-green">
                            {opportunity.recommended_gameweek
                              ? `Best visible window · GW${opportunity.recommended_gameweek}`
                              : "No strong window yet"}
                          </div>
                        </div>
                      </div>
                      <div className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${confidenceClass(opportunity.confidence)}`}>
                        {opportunity.confidence} confidence
                      </div>
                    </div>

                    <h3 className="mt-5 text-lg font-semibold leading-7 text-primary">{opportunity.headline}</h3>
                    <p className="mt-2 text-sm leading-6 text-secondary">{opportunity.summary}</p>

                    {opportunity.why_now.length ? (
                      <div className="mt-4 rounded-lg border border-fpl-green/20 bg-fpl-green/[0.04] p-4">
                        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-fpl-green">Why this window</div>
                        <ul className="mt-3 space-y-2 text-xs leading-5 text-secondary">
                          {opportunity.why_now.map((reason) => (
                            <li key={reason} className="flex gap-2">
                              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-fpl-green" />
                              <span>{reason}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    <div className="mt-4 text-xs leading-5 text-muted">
                      <span className="font-semibold text-secondary">Why you might wait: </span>
                      {opportunity.why_wait}
                    </div>

                    {opportunity.alternatives.length ? (
                      <div className="mt-4 border-t border-fpl-border pt-4">
                        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Alternatives</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {opportunity.alternatives.slice(0, 3).map((_, index) => (
                            <span key={alternativeLabel(opportunity, index)} className="rounded-full border border-fpl-border bg-fpl-raised px-3 py-1 text-xs text-secondary">
                              {alternativeLabel(opportunity, index)}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
            <div className="mt-4 text-xs text-muted">
              {opportunities.model} · data retrieved {opportunities.data_cutoff ?? "live"} · non-personalized · no automatic chip actions
            </div>
          </>
        )}
      </Panel>

      <Panel>
        <div className="mb-4">
          <h2 className="text-[18px] font-semibold text-primary">Your chip inventory</h2>
          <p className="mt-1 text-[13px] text-secondary">
            Connecting a team is used only to show availability and usage—not to generate the recommendations above.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {chipCards.map((chip) => {
            const Icon = chip.icon;
            const available = chip.status === "available";
            return (
              <div key={chip.key} className="rounded-lg border border-fpl-border bg-[#161616] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-primary">{chip.name}</div>
                    <div className="mt-1 text-xs text-muted">{chip.subtitle}</div>
                  </div>
                  <Icon className="h-5 w-5 text-fpl-green" />
                </div>
                <div className={`mt-4 rounded-full border px-3 py-1 text-[11px] ${available ? "border-fpl-green/30 bg-fpl-green/10 text-fpl-green" : "border-fpl-border bg-fpl-raised text-muted"}`}>
                  {chipStatusLabel(chip)}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <div className="mb-4">
          <h2 className="text-[18px] font-semibold text-primary">How each opportunity is identified</h2>
          <p className="mt-1 text-[13px] text-secondary">
            Each chip has different evidence. There is no universal chip threshold.
          </p>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          {methodology.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.name} className="rounded-lg border border-fpl-border bg-[#161616] p-4">
                <div className="flex items-center gap-2 font-semibold text-primary">
                  <Icon className="h-4 w-4 text-fpl-green" />
                  {item.name}
                </div>
                <p className="mt-2 text-sm leading-6 text-secondary">{item.text}</p>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <div className="flex items-start gap-3">
          <CalendarClock className="mt-0.5 h-5 w-5 shrink-0 text-fpl-gold" />
          <div>
            <h2 className="text-[18px] font-semibold text-primary">Timing still changes</h2>
            <p className="mt-2 text-sm leading-6 text-secondary">
              Fixture postponements, doubles, injuries and role changes can move these rankings. Treat the cards as evidence-backed windows to consider, then recheck near the deadline.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
