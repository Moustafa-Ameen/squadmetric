import type { Metadata } from "next";
import { DashboardLoader } from "@/components/DashboardLoader";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return <DashboardLoader />;
}
