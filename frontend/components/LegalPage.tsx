import type { ReactNode } from "react";
import { PublicFooter } from "./PublicFooter";
import { PublicHeader } from "./PublicHeader";

export function LegalPage({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return <div className="marketing-page min-h-screen"><PublicHeader /><main id="main-content" className="px-5 py-14 sm:px-8"><article className="mx-auto max-w-3xl rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-10"><div className="text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Last updated 21 August 2026</div><h1 className="mt-3 text-4xl font-black tracking-[-0.04em] text-slate-950">{title}</h1><p className="mt-5 text-base leading-7 text-slate-600">{intro}</p><div className="legal-copy mt-10 space-y-8 text-sm leading-7 text-slate-700">{children}</div></article></main><PublicFooter /></div>;
}
