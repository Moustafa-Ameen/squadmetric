import type { ReactNode } from "react";
import { Brand } from "./Brand";
import { PublicHeader } from "./PublicHeader";
import { PublicFooter } from "./PublicFooter";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="marketing-page min-h-screen">
      <PublicHeader />
      <main id="main-content" className="grid min-h-[calc(100vh-4.5rem)] lg:grid-cols-[minmax(0,0.9fr)_minmax(520px,1.1fr)]">
        <aside className="auth-story hidden flex-col justify-between overflow-hidden bg-slate-950 p-10 text-white lg:flex xl:p-14">
          <Brand inverse />
          <div className="relative z-10 max-w-lg">
            <div className="inline-flex rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-bold text-emerald-300">A clearer way to play</div>
            <h2 className="mt-6 text-4xl font-black tracking-[-0.045em] xl:text-5xl">One recommendation. Two alternatives. Your decision.</h2>
            <p className="mt-5 text-base leading-7 text-slate-300">SquadMetric prioritizes what matters before the deadline and keeps the deeper analysis within reach—not in your way.</p>
          </div>
          <p className="relative z-10 text-xs leading-5 text-slate-400">Independent fantasy football analytics. Not affiliated with or endorsed by the Premier League.</p>
        </aside>
        <div className="flex items-start justify-center px-5 py-8 sm:px-8 lg:items-center lg:px-12 lg:py-12">{children}</div>
      </main>
      <PublicFooter />
    </div>
  );
}
