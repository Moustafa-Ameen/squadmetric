import type { Metadata } from "next";
import { AuthCard } from "@/components/AuthCard";
import { AuthLayout } from "@/components/AuthLayout";

export const metadata: Metadata = { title: "Reset password" };
export default function ForgotPasswordPage() { return <AuthLayout><AuthCard mode="forgot" /></AuthLayout>; }
