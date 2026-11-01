import type { Metadata } from "next";

export const metadata: Metadata = { title: "Chip Guide" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
