"use client";

import Link from "next/link";
import { ArrowRight, Check, Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { authRedirectUrl, sanitizeNextPath } from "@/lib/auth";
import { LEGAL_VERSION } from "@/lib/legal";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type AuthMode = "login" | "signup" | "forgot";

export function AuthCard({ mode }: { mode: AuthMode }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState("");
  const [statusTone, setStatusTone] = useState<"info" | "error" | "success">("info");
  const [submitting, setSubmitting] = useState(false);
  const [acceptedLegal, setAcceptedLegal] = useState(false);
  const [confirmationEmail, setConfirmationEmail] = useState("");
  const configured = isSupabaseConfigured();

  const emailValid = /^\S+@\S+\.\S+$/.test(email);
  const passwordRules = useMemo(() => ({
    length: password.length >= 8,
    number: /\d/.test(password),
    letter: /[A-Za-z]/.test(password),
  }), [password]);
  const passwordValid = Object.values(passwordRules).every(Boolean);
  const formValid = mode === "forgot" ? emailValid : mode === "login" ? emailValid && password.length > 0 : emailValid && passwordValid && confirmPassword === password && acceptedLegal;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched({ email: true, password: true, confirmPassword: true });
    if (!formValid || submitting) return;
    const supabase = createSupabaseBrowserClient();
    if (!supabase) {
      setStatusTone("error");
      setStatus("Account access is not configured on this deployment. Add the Supabase public environment variables to enable secure sign-in.");
      return;
    }

    setSubmitting(true);
    setStatus("");
    try {
      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        const next = sanitizeNextPath(new URLSearchParams(window.location.search).get("next"), "/dashboard");
        router.replace(next);
        router.refresh();
        return;
      }

      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: authRedirectUrl("/auth/callback?next=/onboarding"),
            data: { legal_accepted: true, terms_version: LEGAL_VERSION, privacy_version: LEGAL_VERSION },
          },
        });
        if (error) throw error;
        if (data.session) {
          router.replace("/onboarding");
          router.refresh();
          return;
        }
        setStatusTone("success");
        setConfirmationEmail(email);
        setStatus("Check your email to confirm your account. The secure link will return you to connect your FPL team.");
        return;
      }

      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: authRedirectUrl("/auth/callback?next=/update-password"),
      });
      if (error) throw error;
      setStatusTone("success");
      setStatus("If an account exists for that email, a secure password-reset link is on its way.");
    } catch (error) {
      setStatusTone("error");
      setStatus(friendlyAuthError(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function resendConfirmation() {
    if (!confirmationEmail || submitting) return;
    const supabase = createSupabaseBrowserClient();
    if (!supabase) return;
    setSubmitting(true);
    try {
      const { error } = await supabase.auth.resend({
        type: "signup",
        email: confirmationEmail,
        options: { emailRedirectTo: authRedirectUrl("/auth/callback?next=/onboarding") },
      });
      if (error) throw error;
      setStatusTone("success");
      setStatus("A fresh confirmation link has been sent. Use the newest email and open the link once.");
    } catch (error) {
      setStatusTone("error");
      setStatus(friendlyAuthError(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function continueWithGoogle() {
    if (submitting) return;
    if (mode === "signup" && !acceptedLegal) {
      setStatusTone("error");
      setStatus("Agree to the Terms of Use and acknowledge the Privacy Policy before continuing.");
      return;
    }
    const supabase = createSupabaseBrowserClient();
    if (!supabase) {
      setStatusTone("error");
      setStatus("Google sign-in is not configured on this deployment yet.");
      return;
    }

    setSubmitting(true);
    setStatus("");
    const next = mode === "signup" ? "/consent" : sanitizeNextPath(new URLSearchParams(window.location.search).get("next"), "/dashboard");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: authRedirectUrl(`/auth/callback?next=${encodeURIComponent(next)}`) },
    });
    if (error) {
      setSubmitting(false);
      setStatusTone("error");
      setStatus(friendlyAuthError(error));
    }
  }

  const copy = {
    login: { eyebrow: "Welcome back", title: "Sign in to SquadMetric", body: "Open your latest gameweek plan and saved decisions.", action: "Sign in", switchText: "New to SquadMetric?", switchAction: "Create an account", switchHref: "/signup" },
    signup: { eyebrow: "Get started", title: "Create your account", body: "Your weekly FPL decisions, drafts, and preferences in one place.", action: "Create account", switchText: "Already have an account?", switchAction: "Sign in", switchHref: "/login" },
    forgot: { eyebrow: "Account recovery", title: "Reset your password", body: "Enter your email and we’ll send you a secure reset link.", action: "Send reset link", switchText: "Remembered your password?", switchAction: "Back to sign in", switchHref: "/login" },
  }[mode];

  return (
    <section className="w-full max-w-[470px] rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_rgba(15,23,42,0.12)] sm:p-8" aria-labelledby="auth-title">
      <div className="text-xs font-bold uppercase tracking-[0.16em] text-violet-700">{copy.eyebrow}</div>
      <h1 id="auth-title" className="mt-3 text-3xl font-black tracking-[-0.04em] text-slate-950">{copy.title}</h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">{copy.body}</p>

      {mode !== "forgot" ? (
        <button type="button" onClick={continueWithGoogle} disabled={submitting} className="mt-7 flex w-full items-center justify-center gap-3 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-800 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60">
          <span className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 text-xs font-black text-blue-600" aria-hidden="true">G</span>
          Continue with Google
        </button>
      ) : null}

      {mode !== "forgot" ? <div className="my-6 flex items-center gap-3 text-xs font-semibold text-slate-600"><span className="h-px flex-1 bg-slate-200" />or continue with email<span className="h-px flex-1 bg-slate-200" /></div> : null}

      <form onSubmit={submit} noValidate className={mode === "forgot" ? "mt-7 space-y-5" : "space-y-5"}>
        <Field id={`${mode}-email`} label="Email address" error={touched.email && !emailValid ? "Enter a valid email address." : ""}>
          <Mail className="auth-field-icon" aria-hidden="true" />
          <input id={`${mode}-email`} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, email: true }))} aria-invalid={touched.email && !emailValid} aria-describedby={touched.email && !emailValid ? `${mode}-email-error` : undefined} className="auth-input" placeholder="you@example.com" />
        </Field>

        {mode !== "forgot" ? (
          <Field id={`${mode}-password`} label="Password" error={touched.password && !password.length ? "Enter your password." : ""} action={mode === "login" ? <Link href="/forgot-password" className="text-xs font-bold text-violet-700 hover:text-violet-900">Forgot password?</Link> : undefined}>
            <LockKeyhole className="auth-field-icon" aria-hidden="true" />
            <input id={`${mode}-password`} type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, password: true }))} className="auth-input pr-12" placeholder="Enter your password" />
            <button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-[39px] text-slate-400 hover:text-slate-700" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}</button>
          </Field>
        ) : null}

        {mode === "signup" ? (
          <>
            <ul className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3" aria-label="Password requirements">
              <Rule met={passwordRules.length}>8+ characters</Rule><Rule met={passwordRules.letter}>One letter</Rule><Rule met={passwordRules.number}>One number</Rule>
            </ul>
            <Field id="signup-confirm-password" label="Confirm password" error={touched.confirmPassword && confirmPassword !== password ? "Passwords do not match." : ""}>
              <LockKeyhole className="auth-field-icon" aria-hidden="true" />
              <input id="signup-confirm-password" type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} onBlur={() => setTouched((value) => ({ ...value, confirmPassword: true }))} className="auth-input" placeholder="Repeat your password" />
            </Field>
            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3"><input type="checkbox" checked={acceptedLegal} onChange={(event) => setAcceptedLegal(event.target.checked)} className="mt-1 h-4 w-4 accent-violet-600" /><span className="text-xs leading-5 text-slate-600">I agree to the <Link href="/terms" target="_blank" className="font-bold text-violet-700 underline">Terms of Use</Link> and acknowledge the <Link href="/privacy" target="_blank" className="font-bold text-violet-700 underline">Privacy Policy</Link>.</span></label>
          </>
        ) : null}

        <button type="submit" disabled={!formValid || submitting} className="sm-primary-button w-full justify-center px-5 py-3.5 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">
          {submitting ? "Please wait…" : copy.action}<ArrowRight className="h-4 w-4" />
        </button>
      </form>

      {!configured && !status ? <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900" role="status">Secure accounts are not configured in this local environment. Product pages remain available for development.</div> : null}
      {status ? <div className={`mt-5 rounded-xl border px-4 py-3 text-sm leading-6 ${statusTone === "error" ? "border-rose-200 bg-rose-50 text-rose-900" : statusTone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-violet-200 bg-violet-50 text-violet-900"}`} role={statusTone === "error" ? "alert" : "status"}>{status}</div> : null}
      {mode === "signup" && confirmationEmail ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <span className="text-xs leading-5 text-slate-600">Didn&apos;t get it, or has the link expired?</span>
          <button type="button" onClick={resendConfirmation} disabled={submitting} className="text-xs font-extrabold text-violet-700 hover:text-violet-900 disabled:opacity-50">
            {submitting ? "Sending…" : "Send a new link"}
          </button>
        </div>
      ) : null}
      <p className="mt-6 text-center text-sm text-slate-600">{copy.switchText} <Link href={copy.switchHref} className="font-bold text-violet-700 hover:text-violet-900">{copy.switchAction}</Link></p>
    </section>
  );
}

function friendlyAuthError(error: unknown): string {
  const message = error instanceof Error ? error.message : "Authentication failed.";
  if (/invalid login credentials/i.test(message)) return "The email or password is incorrect.";
  if (/email not confirmed/i.test(message)) return "Confirm your email before signing in.";
  if (/already registered/i.test(message)) return "An account already exists for this email. Try signing in.";
  if (/rate limit/i.test(message)) return "Too many attempts. Wait a moment and try again.";
  return "We could not complete that secure account request. Please try again.";
}

function Field({ id, label, error, action, children }: { id: string; label: string; error: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <div className="relative"><div className="mb-2 flex items-center justify-between gap-3"><label htmlFor={id} className="text-sm font-bold text-slate-800">{label}</label>{action}</div>{children}{error ? <p id={`${id}-error`} className="mt-2 text-xs font-semibold text-rose-700" role="alert">{error}</p> : null}</div>;
}

function Rule({ met, children }: { met: boolean; children: React.ReactNode }) {
  return <li className={`flex items-center gap-1.5 ${met ? "font-semibold text-emerald-700" : ""}`}><span className={`flex h-4 w-4 items-center justify-center rounded-full ${met ? "bg-emerald-100" : "bg-slate-100"}`}>{met ? <Check className="h-2.5 w-2.5" /> : null}</span>{children}</li>;
}
