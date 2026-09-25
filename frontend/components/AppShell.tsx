"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { DrawerProvider } from "@/context/DrawerContext";
import { getSeasonState } from "@/lib/api";
import type { SeasonState } from "@/lib/types";
import { AppNavigation } from "./AppNavigation";
import { AccountSessionHydrator } from "./AccountSessionHydrator";
import { DecisionStatusNotice } from "./DecisionStatusNotice";
import { PlayerDrawer } from "./PlayerDrawer";

const SHELLLESS_ROUTES = new Set(["/", "/login", "/signup", "/forgot-password", "/update-password", "/onboarding", "/consent", "/privacy", "/terms", "/auth/error"]);
const ROUTES_WITH_OWN_STATUS = new Set(["/dashboard", "/decisions"]);

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const publicRoute = SHELLLESS_ROUTES.has(pathname);
  const pageOwnsStatus = ROUTES_WITH_OWN_STATUS.has(pathname);
  const [seasonState, setSeasonState] = useState<SeasonState | null>(null);
  const [seasonStateError, setSeasonStateError] = useState(false);

  useEffect(() => {
    if (publicRoute) return;
    getSeasonState()
      .then((state) => {
        setSeasonState(state);
        setSeasonStateError(false);
      })
      .catch(() => {
        setSeasonState(null);
        setSeasonStateError(true);
      });
  }, [publicRoute]);

  if (publicRoute) return children;

  return (
    <DrawerProvider>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <AppNavigation />
      <main id="main-content" tabIndex={-1} className="decision-grid min-h-[calc(100vh-4.5rem)] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-8">
        <div className="mx-auto max-w-[1280px]">
          {seasonState && !seasonState.recommendations_ready && !pageOwnsStatus ? <div className="mb-5"><DecisionStatusNotice seasonState={seasonState} compact /></div> : null}
          {seasonStateError ? (
            <div className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
              Live decision status is unavailable. Existing content remains visible, but confirm freshness before acting.
            </div>
          ) : null}
          <AccountSessionHydrator>{children}</AccountSessionHydrator>
        </div>
      </main>
      <PlayerDrawer />
    </DrawerProvider>
  );
}
