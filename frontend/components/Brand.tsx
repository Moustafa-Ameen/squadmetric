import Link from "next/link";
import { ChartNoAxesCombined } from "lucide-react";

export function Brand({ compact = false, href = "/", inverse = false }: { compact?: boolean; href?: string; inverse?: boolean }) {
  return (
    <Link href={href} className="inline-flex items-center gap-3 rounded-lg focus-visible:outline-offset-4" aria-label="SquadMetric home">
      <span className="brand-mark" aria-hidden="true">
        <ChartNoAxesCombined className="h-5 w-5" strokeWidth={2.4} />
      </span>
      <span className="leading-none">
        <span className={`block text-[17px] font-black tracking-[-0.035em] ${inverse ? "text-white" : "text-slate-950"}`}>SquadMetric</span>
        {!compact ? <span className={`mt-1 block text-[10px] font-bold uppercase tracking-[0.13em] ${inverse ? "text-slate-400" : "text-slate-500"}`}>Smarter FPL Decisions</span> : null}
      </span>
    </Link>
  );
}
