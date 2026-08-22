import Link from "next/link";
import { AuthLayout } from "@/components/AuthLayout";

export default function AuthErrorPage() {
  return (
    <AuthLayout>
      <section className="w-full max-w-[470px] rounded-[28px] border border-rose-200 bg-white p-8 shadow-[0_24px_70px_rgba(15,23,42,0.12)]">
        <div className="text-xs font-bold uppercase tracking-[0.16em] text-rose-700">Secure link problem</div>
        <h1 className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950">We could not complete sign-in</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">The link may have expired or the account provider may not be configured. Start again to request a fresh secure link.</p>
        <Link href="/login" className="sm-primary-button mt-7 inline-flex px-5 py-3">Return to sign in</Link>
      </section>
    </AuthLayout>
  );
}
