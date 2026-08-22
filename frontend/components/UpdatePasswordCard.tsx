"use client";

import { Check, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function UpdatePasswordCard() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const rules = useMemo(() => ({ length: password.length >= 8, letter: /[A-Za-z]/.test(password), number: /\d/.test(password) }), [password]);
  const valid = Object.values(rules).every(Boolean) && password === confirm;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || busy) return;
    const supabase = createSupabaseBrowserClient();
    if (!supabase) {
      setStatus("Secure accounts are not configured on this deployment.");
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.updateUser({ password });
    setBusy(false);
    if (error) {
      setStatus("The reset session has expired. Request a new password-reset email.");
      return;
    }
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <section className="w-full max-w-[470px] rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_24px_70px_rgba(15,23,42,0.12)]">
      <div className="text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Account recovery</div>
      <h1 className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950">Choose a new password</h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">Use at least eight characters with a letter and a number.</p>
      <form onSubmit={submit} className="mt-7 space-y-5">
        <label className="relative block"><span className="mb-2 block text-sm font-bold text-slate-800">New password</span><LockKeyhole className="auth-field-icon" aria-hidden="true" /><input aria-label="New password" type={show ? "text" : "password"} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className="auth-input pr-12" /><button type="button" onClick={() => setShow((value) => !value)} className="absolute right-3 top-[39px] text-slate-400" aria-label={show ? "Hide password" : "Show password"}>{show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}</button></label>
        <ul className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3" aria-label="Password requirements">{Object.entries({ "8+ characters": rules.length, "One letter": rules.letter, "One number": rules.number }).map(([label, met]) => <li key={label} className={met ? "flex items-center gap-1.5 font-semibold text-emerald-700" : "flex items-center gap-1.5"}><span className={met ? "flex h-4 w-4 items-center justify-center rounded-full bg-emerald-100" : "h-4 w-4 rounded-full bg-slate-100"}>{met ? <Check className="h-2.5 w-2.5" /> : null}</span>{label}</li>)}</ul>
        <label className="relative block"><span className="mb-2 block text-sm font-bold text-slate-800">Confirm password</span><LockKeyhole className="auth-field-icon" aria-hidden="true" /><input aria-label="Confirm password" type={show ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} className="auth-input" /></label>
        {confirm && confirm !== password ? <p className="text-xs font-semibold text-rose-700" role="alert">Passwords do not match.</p> : null}
        <button type="submit" disabled={!valid || busy} className="sm-primary-button w-full justify-center px-5 py-3.5 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">{busy ? "Updating…" : "Update password"}</button>
      </form>
      {status ? <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900" role="alert">{status}</div> : null}
    </section>
  );
}
