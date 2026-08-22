import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SquadMetric — Smarter FPL Decisions",
    template: "%s | SquadMetric",
  },
  description:
    "Clear, confidence-aware FPL recommendations for transfers, captaincy, your bench, and chips.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
