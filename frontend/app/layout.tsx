import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim() || "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: "SquadMetric",
  title: {
    default: "SquadMetric — Smarter FPL Decisions",
    template: "%s | SquadMetric",
  },
  description:
    "Clear, confidence-aware FPL recommendations for transfers, captaincy, your bench, and chips.",
  keywords: ["Fantasy Premier League", "FPL", "FPL team rating", "FPL transfers", "FPL captain"],
  openGraph: {
    type: "website",
    url: "/",
    siteName: "SquadMetric",
    title: "SquadMetric — Smarter FPL Decisions",
    description: "Rate your FPL squad and turn projections into clear transfer, captaincy, bench, and chip decisions.",
  },
  twitter: {
    card: "summary_large_image",
    title: "SquadMetric — Smarter FPL Decisions",
    description: "Rate your FPL squad and get clear, evidence-backed decisions for every gameweek.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
