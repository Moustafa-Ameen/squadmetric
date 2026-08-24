import type { ReactNode } from "react";

interface PanelProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, children, className = "" }: PanelProps) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_10px_35px_rgba(15,23,42,0.06)] sm:p-6 ${className}`}>
      {title ? (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-extrabold text-slate-950">{title}</h2>
          <span className="h-px min-w-8 flex-1 bg-gradient-to-r from-slate-200 to-transparent" />
        </div>
      ) : null}
      {children}
    </section>
  );
}
