"use client";

import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

// A <details> dropdown that also closes on an outside click, Escape, or choosing
// a link inside it; native <details> only closes when its summary is clicked.
export function DismissibleMenu({ summary, children, className = "relative" }: { summary: ReactNode; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    function close() {
      if (ref.current?.open) ref.current.open = false;
    }
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && ref.current?.open) {
        close();
        ref.current.querySelector("summary")?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <details
      ref={ref}
      className={className}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest("a") && ref.current) ref.current.open = false;
      }}
    >
      {summary}
      {children}
    </details>
  );
}
