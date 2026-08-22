import Link from "next/link";
import { Brand } from "./Brand";

export function PublicHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 px-5 backdrop-blur-xl sm:px-8 lg:px-10">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="mx-auto flex h-18 max-w-7xl items-center justify-between gap-4">
        <Brand />
        <nav aria-label="Public navigation" className="hidden items-center gap-7 md:flex">
          <Link href="/#how-it-works" className="text-sm font-semibold text-slate-600 hover:text-slate-950">How it works</Link>
          <Link href="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-950">Sign in</Link>
          <Link href="/signup" className="sm-primary-button px-4 py-2.5">Get started</Link>
        </nav>
        <div className="md:hidden"><Link href="/login" className="sm-secondary-button px-4 py-2.5">Sign in</Link></div>
      </div>
    </header>
  );
}
