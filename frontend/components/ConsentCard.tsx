"use client";

import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LEGAL_VERSION } from "@/lib/legal";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function ConsentCard() {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    if (!supabase) return;
    void supabase.auth.getUser().then(async ({ data }) => {
      if (!data.user) return;
      const profile = await supabase.from("profiles").select("terms_accepted_at").eq("user_id", data.user.id).maybeSingle();
      if (profile.data?.terms_accepted_at) router.replace("/onboarding");
    });
  }, [router]);

  async function continueSetup() {
    const supabase = createSupabaseBrowserClient();
    if (!supabase || !accepted || busy) return;
    setBusy(true);
    setError("");
    const { data } = await supabase.auth.getUser();
    if (!data.user) {
      router.replace("/login?next=/consent");
      return;
    }
    const { error: saveError } = await supabase.from("profiles").upsert({
      user_id: data.user.id,
      terms_version: LEGAL_VERSION,
      privacy_version: LEGAL_VERSION,
      terms_accepted_at: new Date().toISOString(),
    });
    if (saveError) {
      setError("We could not record your agreement. Please try again.");
      setBusy(false);
      return;
    }
    router.replace("/onboarding");
    router.refresh();
  }

  return <section className="w-full max-w-[520px] rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_rgba(15,23,42,0.12)] sm:p-8"><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-700"><ShieldCheck className="h-6 w-6" /></div><div className="mt-5 text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Before account setup</div><h1 className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950">Your data, your decision</h1><p className="mt-3 text-sm leading-6 text-slate-600">Review how SquadMetric stores account data and the limits of statistical FPL recommendations.</p><label className="mt-7 flex cursor-pointer items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4"><input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} className="mt-1 h-4 w-4 accent-violet-600" /><span className="text-sm leading-6 text-slate-700">I agree to the <Link href="/terms" target="_blank" className="font-bold text-violet-700 underline">Terms of Use</Link> and acknowledge the <Link href="/privacy" target="_blank" className="font-bold text-violet-700 underline">Privacy Policy</Link>.</span></label><button type="button" onClick={continueSetup} disabled={!accepted || busy} className="sm-primary-button mt-6 w-full justify-center px-5 py-3.5 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">{busy ? "Saving…" : "Agree and continue"}<ArrowRight className="h-4 w-4" /></button>{error ? <p className="mt-4 text-sm font-semibold text-rose-700" role="alert">{error}</p> : null}</section>;
}
