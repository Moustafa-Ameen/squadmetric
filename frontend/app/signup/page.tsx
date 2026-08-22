import type { Metadata } from "next";
import { AuthCard } from "@/components/AuthCard";
import { AuthLayout } from "@/components/AuthLayout";

export const metadata: Metadata = { title: "Create account" };
export default function SignupPage() { return <AuthLayout><AuthCard mode="signup" /></AuthLayout>; }
