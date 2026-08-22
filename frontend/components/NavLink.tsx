"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface NavLinkProps {
  href: string;
  children: ReactNode;
  icon: LucideIcon;
  onNavigate?: () => void;
}

export function NavLink({ href, children, icon: Icon, onNavigate }: NavLinkProps) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`mx-2 flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 text-[13px] transition md:justify-center md:px-0 lg:justify-start lg:px-3 ${
        active
          ? "border-fpl-green/25 bg-fpl-green/10 text-fpl-green shadow-[0_0_18px_rgba(0,255,135,0.08)]"
          : "text-secondary hover:bg-white/[0.04] hover:text-primary"
      }`}
      title={String(children)}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="md:hidden lg:inline">{children}</span>
    </Link>
  );
}
