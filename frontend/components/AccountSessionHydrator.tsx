"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { hydrateAccountStorage } from "@/lib/accountStorage";
import { isSupabaseConfigured } from "@/lib/supabase/config";

export function AccountSessionHydrator({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(() => !isSupabaseConfigured());

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    let active = true;

    async function hydrate() {
      let redirecting = false;
      try {
        const result = await hydrateAccountStorage();
        if (result.requiresConsent && pathname !== "/consent") {
          redirecting = true;
          router.replace("/consent");
          return;
        }
        if (result.authenticated && result.requiresOnboarding && pathname !== "/onboarding") {
          redirecting = true;
          router.replace("/onboarding");
          return;
        }
      } catch {
        // Keep locally stored work available when account sync is temporarily unavailable.
      } finally {
        if (active && !redirecting) setReady(true);
      }
    }

    void hydrate();
    return () => { active = false; };
  }, [pathname, router]);

  if (!ready) return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600" role="status">Loading your SquadMetric account…</div>;
  return children;
}
