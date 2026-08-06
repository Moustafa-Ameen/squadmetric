"use client";

import { Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { DrawerProvider } from "@/context/DrawerContext";
import { getSeasonState } from "@/lib/api";
import type { SeasonState } from "@/lib/types";
import { LiveMatchBar } from "./LiveMatchBar";
import { LogoLoader } from "./LogoLoader";
import { PlayerDrawer } from "./PlayerDrawer";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [progressState, setProgressState] = useState<"idle" | "loading" | "done">("loading");
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    queueMicrotask(() => setProgressState("loading"));
    const doneTimer = window.setTimeout(() => setProgressState("done"), 5000);
    const idleTimer = window.setTimeout(() => setProgressState("idle"), 5600);
    return () => {
      window.clearTimeout(doneTimer);
      window.clearTimeout(idleTimer);
    };
  }, [pathname]);

  useEffect(() => {
    getSeasonState().then(setSeasonState).catch(() => setSeasonState(null));
  }, []);

  return (
    <DrawerProvider>
      {progressState !== "idle" ? <LogoLoader complete={progressState === "done"} /> : null}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        className="fixed left-3 top-3 z-40 rounded-lg border border-fpl-border bg-fpl-card p-2 text-fpl-green shadow-lg md:hidden"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      <main className="decision-grid min-h-screen px-4 pb-4 pt-16 md:ml-[76px] md:px-6 md:py-4 lg:ml-[244px] lg:px-9 lg:py-7">
        <div className="mx-auto max-w-[1400px]">
          <LiveMatchBar />
          {seasonState ? (
            <div
              className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
                seasonState.recommendations_ready === false
                  ? "border-fpl-red/40 bg-fpl-red/10 text-fpl-red"
                  : "border-fpl-green/30 bg-fpl-green/10 text-secondary"
              }`}
            >
              <span className="font-semibold text-primary">
                {seasonState.fpl_api_season} FPL
              </span>
              {" · "}
              {seasonState.recommendations_ready === false
                ? `Recommendations blocked: ${(seasonState.artifact_errors ?? []).join("; ")}`
                : seasonState.season_state === "pre_season"
                  ? "Pre-season data, official prices and fixtures loaded"
                  : "Current-season artifacts ready"}
            </div>
          ) : null}
          {children}
        </div>
      </main>
      <PlayerDrawer />
    </DrawerProvider>
  );
}
