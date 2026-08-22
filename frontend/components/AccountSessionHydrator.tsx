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
      try {
        const result = await hydrateAccountStorage();
        if (result.requiresConsent && pathname !== "/consent") {
          router.replace("/consent");
          return;
        }
      } catch {
        // Keep locally stored work available when account sync is temporarily unavailable.
      } finally {
        if (active) setReady(true);
      }
    }

    void hydrate();
    return () => { active = false; };
  }, [pathname, router]);

  if (!ready) return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600" role="status">Loading your SquadMetric account…</div>;
  return children;
}
