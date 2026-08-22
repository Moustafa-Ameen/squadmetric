"use client";

import {
  BarChart3,
  CalendarDays,
  CalendarRange,
  Clock3,
  ClipboardList,
  ListChecks,
  Crown,
  GitCompare,
  Edit2,
  Home,
  Settings,
  Shield,
  ScanSearch,
  TrendingUp,
  Trophy,
  Users,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { getCurrentGameweek, getHealth } from "@/lib/api";
import { NavLink } from "./NavLink";
import { PLLogo } from "./PLLogo";

const navGroups = [
  {
    label: "Main",
    items: [
      { href: "/", label: "Overview", icon: Home },
      { href: "/decisions", label: "This Week", icon: ListChecks },
      { href: "/deadline", label: "Deadline Center", icon: Clock3 },
      { href: "/squad", label: "My Squad", icon: Shield },
      { href: "/drafts", label: "Draft Workspace", icon: ClipboardList },
    ],
  },
  {
    label: "Decisions",
    items: [
      { href: "/captain", label: "Who to Captain", icon: Crown },
      { href: "/transfers", label: "Who to Sign", icon: TrendingUp },
      { href: "/planner", label: "Transfer Planner", icon: CalendarRange },
      { href: "/fixtures", label: "Fixtures", icon: CalendarDays },
      { href: "/chips", label: "Chip Guide", icon: Zap },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/stats", label: "All Players", icon: Users },
      { href: "/compare", label: "Compare Players", icon: GitCompare },
      { href: "/proof", label: "Proof It Works", icon: BarChart3 },
      { href: "/review", label: "Post-GW Review", icon: ScanSearch },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar({
  mobileOpen,
  onCloseMobile,
}: {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const [gameweek, setGameweek] = useState<number | null>(null);
  const [teamId, setTeamId] = useState("");
  const [draftId, setDraftId] = useState("");
  const [apiOk, setApiOk] = useState(false);

  useEffect(() => {
    getCurrentGameweek()
      .then((data) => setGameweek(data.current_gw ?? null))
      .catch(() => setGameweek(null));
    getHealth()
      .then(() => setApiOk(true))
      .catch(() => setApiOk(false));

    queueMicrotask(() => {
      const saved = window.localStorage.getItem("fpl_team_id") ?? "";
      setTeamId(saved);
      setDraftId(saved);
    });
  }, []);

  function saveTeamId() {
    const clean = draftId.trim();
    if (!clean) return;
    window.localStorage.setItem("fpl_team_id", clean);
    setTeamId(clean);
  }

  function editTeamId() {
    window.localStorage.removeItem("fpl_team_id");
    setTeamId("");
  }

  return (
    <>
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          onClick={onCloseMobile}
          className="fixed inset-0 z-30 bg-black/70 md:hidden"
        />
      ) : null}
      <aside
        aria-label="Primary navigation"
        className={`fixed inset-y-0 left-0 z-40 flex w-[244px] flex-col border-r border-white/10 bg-[#070b0a]/96 shadow-[18px_0_60px_rgba(0,0,0,0.45)] backdrop-blur transition-transform md:translate-x-0 md:w-[76px] lg:w-[244px] ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="Close menu"
          className="absolute right-3 top-3 rounded p-1 text-muted hover:text-primary md:hidden"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="px-4 pt-5 md:px-3 lg:px-4">
          <div className="rounded-xl border border-white/10 bg-[linear-gradient(145deg,rgba(255,255,255,0.08),rgba(0,255,135,0.04))] p-3 shadow-[0_18px_42px_rgba(0,0,0,0.28)]">
            <div className="flex items-center gap-3">
              <span className="flex h-[52px] w-[72px] shrink-0 items-center justify-center rounded-lg bg-white px-2 py-1 shadow-[0_0_24px_rgba(255,255,255,0.18)]">
                <PLLogo size={62} height={34} />
              </span>
              <span className="leading-tight md:hidden lg:inline">
                <span className="block text-[18px] font-black tracking-tight text-primary">FPL</span>
                <span className="block text-[15px] font-black uppercase tracking-[0.04em] text-fpl-green">
                  Intelligence
                </span>
              </span>
            </div>
          </div>
          <div className="mt-3 inline-flex rounded-full border border-fpl-border bg-fpl-raised px-3 py-1 text-xs text-secondary md:hidden lg:inline-flex">
            {gameweek ? `GW ${gameweek}` : "GW —"}
          </div>
        </div>

        <nav aria-label="FPL Intelligence sections" className="mt-5 space-y-6">
          {navGroups.map((group) => (
            <div key={group.label}>
              <div className="mb-2 px-5 text-[10px] font-bold uppercase tracking-[0.08em] text-muted md:hidden lg:block">
                {group.label}
              </div>
              <div className="space-y-1">
                {group.items.map((item) => (
                  <NavLink key={item.href} href={item.href} icon={item.icon} onNavigate={onCloseMobile}>
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto border-t border-fpl-border p-4 md:px-2 lg:p-4">
          <div className="md:hidden lg:block">
            {teamId ? (
              <div>
                <div className="text-xs font-semibold text-fpl-green">Team #{teamId} saved</div>
                <button
                  type="button"
                  onClick={editTeamId}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-muted hover:text-primary"
                >
                  <Edit2 className="h-3 w-3" />
                  edit
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <input
                  value={draftId}
                  onChange={(event) => setDraftId(event.target.value)}
                  placeholder="Enter FPL Team ID"
                  className="w-full rounded-lg border border-fpl-border bg-fpl-raised px-3 py-2 text-xs text-primary outline-none focus:border-fpl-green"
                />
                <button type="button" onClick={saveTeamId} className="fpl-button w-full px-3 py-2 text-xs">
                  Confirm
                </button>
              </div>
            )}
            <div className="mt-4 flex items-center gap-2 text-[11px] text-muted">
              <span
                className={`h-2 w-2 rounded-full ${
                  apiOk ? "bg-fpl-green shadow-[0_0_12px_rgba(0,255,135,0.7)]" : "bg-fpl-red"
                }`}
              />
              Data from FPL Official API
            </div>
          </div>
          <Trophy className="mx-auto hidden h-5 w-5 text-fpl-green md:block lg:hidden" />
        </div>
      </aside>
    </>
  );
}
