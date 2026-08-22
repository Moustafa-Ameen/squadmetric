"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  CalendarDays,
  ChevronDown,
  Home,
  Menu,
  Settings,
  Shield,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { Brand } from "./Brand";
import { AccountMenu } from "./AccountMenu";

const primary = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/squad", label: "My Team", icon: Shield },
  { href: "/decisions", label: "Gameweek Plan", icon: Sparkles },
  { href: "/stats", label: "Players", icon: Users },
  { href: "/fixtures", label: "Fixtures", icon: CalendarDays },
];

const secondary = [
  { href: "/planner", label: "Transfer planner" },
  { href: "/drafts", label: "Draft workspace" },
  { href: "/review", label: "Decision history" },
  { href: "/proof", label: "Model performance" },
  { href: "/settings", label: "Settings" },
];

export function AppNavigation() {
  const pathname = usePathname();
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
        <div className="mx-auto flex h-18 max-w-[1440px] items-center gap-6">
          <Brand compact href="/dashboard" />
          <nav aria-label="Primary navigation" className="hidden min-w-0 flex-1 items-center justify-center gap-1 lg:flex">
            {primary.map((item) => <DesktopNavItem key={item.href} {...item} pathname={pathname} />)}
            <details className="relative">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-950">
                More <ChevronDown className="h-4 w-4" />
              </summary>
              <div className="absolute right-0 top-12 w-56 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl">
                {secondary.map((item) => (
                  <Link key={item.href} href={item.href} className="block rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-950">{item.label}</Link>
                ))}
              </div>
            </details>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 sm:inline">2026/27 live</span>
            <AccountMenu />
          </div>
        </div>
      </header>

      <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-slate-200 bg-white/98 px-2 pb-[max(0.45rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-10px_30px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden">
        {primary.slice(0, 4).map((item) => <MobileNavItem key={item.href} {...item} pathname={pathname} />)}
        <button type="button" onClick={() => setMobileMoreOpen(true)} aria-expanded={mobileMoreOpen} className="flex min-h-12 flex-col items-center justify-center gap-1 rounded-xl text-[10px] font-bold text-slate-500 hover:bg-slate-100 hover:text-slate-950">
          <Menu className="h-5 w-5" /> More
        </button>
      </nav>

      {mobileMoreOpen ? (
        <div className="fixed inset-0 z-[60] bg-slate-950/45 p-4 backdrop-blur-sm lg:hidden" role="presentation" onClick={() => setMobileMoreOpen(false)}>
          <section role="dialog" aria-modal="true" aria-label="More navigation" className="absolute inset-x-3 bottom-3 rounded-3xl bg-white p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between px-2 pb-3">
              <div><div className="font-bold text-slate-950">More from SquadMetric</div><div className="mt-1 text-xs text-slate-500">Planning, history, and account tools</div></div>
              <button type="button" onClick={() => setMobileMoreOpen(false)} aria-label="Close menu" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-600"><X className="h-5 w-5" /></button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Link href="/fixtures" onClick={() => setMobileMoreOpen(false)} className="mobile-more-link"><CalendarDays className="h-5 w-5" /> Fixtures</Link>
              <Link href="/planner" onClick={() => setMobileMoreOpen(false)} className="mobile-more-link"><BarChart3 className="h-5 w-5" /> Transfer planner</Link>
              <Link href="/review" onClick={() => setMobileMoreOpen(false)} className="mobile-more-link"><Sparkles className="h-5 w-5" /> Decision history</Link>
              <Link href="/settings" onClick={() => setMobileMoreOpen(false)} className="mobile-more-link"><Settings className="h-5 w-5" /> Settings</Link>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

function DesktopNavItem({ href, label, icon: Icon, pathname }: { href: string; label: string; icon: typeof Home; pathname: string }) {
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return <Link href={href} aria-current={active ? "page" : undefined} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold ${active ? "bg-violet-50 text-violet-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`}><Icon className="h-4 w-4" />{label}</Link>;
}

function MobileNavItem({ href, label, icon: Icon, pathname }: { href: string; label: string; icon: typeof Home; pathname: string }) {
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return <Link href={href} aria-current={active ? "page" : undefined} className={`flex min-h-12 flex-col items-center justify-center gap-1 rounded-xl text-[10px] font-bold ${active ? "bg-violet-50 text-violet-700" : "text-slate-500 hover:bg-slate-100 hover:text-slate-950"}`}><Icon className="h-5 w-5" />{label === "Gameweek Plan" ? "Plan" : label}</Link>;
}
