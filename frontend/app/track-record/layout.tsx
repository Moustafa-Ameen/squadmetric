import type { Metadata } from "next";

export const metadata: Metadata = { title: "Track Record" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
