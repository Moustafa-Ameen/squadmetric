import Link from "next/link";
import { Brand } from "./Brand";

export function PublicFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white px-5 py-8 sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <Brand compact />
        <div className="flex flex-col gap-3 sm:items-end">
          <nav aria-label="Legal" className="flex gap-5"><Link href="/privacy" className="font-semibold hover:text-slate-950">Privacy</Link><Link href="/terms" className="font-semibold hover:text-slate-950">Terms</Link></nav>
          <p>Independent fantasy football analytics. Not affiliated with or endorsed by the Premier League.</p>
        </div>
      </div>
    </footer>
  );
}
