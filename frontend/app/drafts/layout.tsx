import type { Metadata } from "next";

export const metadata: Metadata = { title: "Draft Workspace" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
