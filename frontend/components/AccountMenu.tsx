"use client";

import Link from "next/link";
import { CircleUserRound, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

export function AccountMenu() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const configured = isSupabaseConfigured();

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    if (!supabase) return;
    let active = true;
    supabase.auth.getUser().then(({ data }) => {
      if (active) setEmail(data.user?.email ?? null);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) setEmail(session?.user.email ?? null);
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  async function signOut() {
    const supabase = createSupabaseBrowserClient();
    if (supabase) await supabase.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <details className="relative">
      <summary aria-label="Account menu" className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-slate-200 bg-slate-50 p-1.5 text-slate-600 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 sm:pr-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white"><CircleUserRound className="h-5 w-5" /></span>
        <span className="hidden max-w-40 truncate text-xs font-bold sm:block">{email ?? (configured ? "Account" : "Local mode")}</span>
      </summary>
      <div className="absolute right-0 top-12 z-50 w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
        <div className="px-3 py-2"><div className="text-xs font-bold uppercase tracking-wider text-slate-400">{configured ? "Signed in as" : "Development mode"}</div><div className="mt-1 truncate text-sm font-semibold text-slate-800">{email ?? (configured ? "Loading account…" : "Supabase not configured")}</div></div>
        <Link href="/settings" className="block rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Account settings</Link>
        <Link href="/onboarding" className="block rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Connect FPL team</Link>
        {email ? <button type="button" onClick={signOut} className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-50"><LogOut className="h-4 w-4" />Sign out</button> : null}
      </div>
    </details>
  );
}
