import type { Metadata } from "next";
import { AuthCard } from "@/components/AuthCard";
import { AuthLayout } from "@/components/AuthLayout";

export const metadata: Metadata = { title: "Sign in" };
export default function LoginPage() { return <AuthLayout><AuthCard mode="login" /></AuthLayout>; }
