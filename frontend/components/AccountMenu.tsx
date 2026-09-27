"use client";

import Link from "next/link";
import { CircleUserRound } from "lucide-react";

export function AccountMenu() {
  return (
    <details className="relative">
      <summary aria-label="Profile menu" className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-slate-200 bg-slate-50 p-1.5 text-slate-600 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 sm:pr-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white"><CircleUserRound className="h-5 w-5" /></span>
        <span className="hidden max-w-40 truncate text-xs font-bold sm:block">Profile</span>
      </summary>
      <div className="absolute right-0 top-12 z-50 w-64 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
        <div className="px-3 py-2"><div className="text-xs font-bold uppercase tracking-wider text-slate-400">Browser profile</div><div className="mt-1 truncate text-sm font-semibold text-slate-800">Saved on this device</div></div>
        <Link href="/settings" className="block rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Settings</Link>
        <Link href="/onboarding" className="block rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Connect FPL team</Link>
      </div>
    </details>
  );
}
