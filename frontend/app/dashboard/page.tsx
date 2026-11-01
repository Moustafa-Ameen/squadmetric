import type { Metadata } from "next";
import { DashboardLoader } from "@/components/DashboardLoader";

export const metadata: Metadata = {
  title: "My Team",
};

export default function DashboardPage() {
  return <DashboardLoader />;
}
