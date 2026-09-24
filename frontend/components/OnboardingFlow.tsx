"use client";

import { ArrowLeft, ArrowRight, Bell, CheckCircle2, ShieldCheck, Trophy } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { getTeam } from "@/lib/api";
import { DEFAULT_ONBOARDING_PREFERENCES, persistOnboarding, persistProvisionalOnboarding, type OnboardingPreferences } from "@/lib/account";
import { parseFplTeamInput, type ParsedFplTeam } from "@/lib/fplTeam";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import type { ScreenshotAnalysis, TeamData } from "@/lib/types";
import { ScreenshotTeamImport } from "./ScreenshotTeamImport";

export function OnboardingFlow() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [teamInput, setTeamInput] = useState("");
  const [parsedTeam, setParsedTeam] = useState<ParsedFplTeam | null>(null);
  const [team, setTeam] = useState<TeamData | null>(null);
  const [screenshotAnalysis, setScreenshotAnalysis] = useState<ScreenshotAnalysis | null>(null);
  const [preferences, setPreferences] = useState<OnboardingPreferences>(DEFAULT_ONBOARDING_PREFERENCES);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const configured = isSupabaseConfigured();

  async function verifyTeam(event: React.FormEvent) {
    event.preventDefault();
    const parsed = parseFplTeamInput(teamInput);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }

    setBusy(true);
    setError("");
    try {
      const verified = await getTeam(parsed.value.teamId);
      setParsedTeam(parsed.value);
      setTeam(verified);
      setStep(2);
    } catch {
      setError("We could not verify that team with the official FPL data service. Check the ID and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if ((!screenshotAnalysis && (!parsedTeam || !team)) || busy) return;
    setBusy(true);
    setError("");
    try {
      if (screenshotAnalysis) {
        await persistProvisionalOnboarding({ supabase: createSupabaseBrowserClient(), analysis: screenshotAnalysis, preferences });
      } else if (parsedTeam && team) {
        await persistOnboarding({
          supabase: createSupabaseBrowserClient(),
          teamId: parsedTeam.teamId,
          sourceInput: teamInput.trim(),
          team,
          preferences,
        });
      }
      router.replace("/dashboard");
      router.refresh();
    } catch {
      setError("Your team was verified, but we could not save it securely to your account. Please try again.");
      setBusy(false);
    }
  }

  return (
    <section className="w-full max-w-2xl rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_rgba(15,23,42,0.12)] sm:p-8" aria-labelledby="onboarding-title">
      <div className="flex items-center justify-between gap-4">
        <div><div className="text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Account setup</div><h1 id="onboarding-title" className="mt-2 text-3xl font-black tracking-[-0.04em] text-slate-950">Personalize SquadMetric</h1></div>
        <span className="shrink-0 whitespace-nowrap rounded-full bg-violet-50 px-3 py-1.5 text-xs font-bold text-violet-700">Step {step} of 3</span>
      </div>
      <div className="mt-6 grid grid-cols-3 gap-2" aria-hidden="true">{[1, 2, 3].map((value) => <span key={value} className={`h-1.5 rounded-full ${value <= step ? "bg-violet-600" : "bg-slate-200"}`} />)}</div>

      {step === 1 ? (
        <form onSubmit={verifyTeam} className="mt-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700"><Trophy className="h-6 w-6" /></div>
          <h2 className="mt-5 text-xl font-black text-slate-950">Connect your FPL team</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">Paste your numeric Team ID or any official team URL. This is public FPL data; SquadMetric never asks for your FPL password.</p>
          <label htmlFor="fpl-team-input" className="mt-6 block text-sm font-bold text-slate-800">FPL Team ID or URL</label>
          <input id="fpl-team-input" value={teamInput} onChange={(event) => setTeamInput(event.target.value)} placeholder="123456 or fantasy.premierleague.com/en/entry/123456/event/4" className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-100" aria-describedby="team-input-help" />
          <p id="team-input-help" className="mt-2 text-xs leading-5 text-slate-500">Points, history, transfers, localized `/en/` links, and the numeric Team ID are all accepted.</p>
          <button type="submit" disabled={!teamInput.trim() || busy} className="sm-primary-button mt-6 w-full justify-center px-5 py-3.5 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">{busy ? "Verifying…" : "Verify team"}<ArrowRight className="h-4 w-4" /></button>
          <div className="my-6 flex items-center gap-3"><span className="h-px flex-1 bg-slate-200" /><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">or</span><span className="h-px flex-1 bg-slate-200" /></div>
          <ScreenshotTeamImport onAnalyzed={(analysis) => { setScreenshotAnalysis(analysis); setParsedTeam(null); setTeam(null); setStep(2); }} />
        </form>
      ) : null}

      {step === 2 ? (
        <div className="mt-8">
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><div className="flex items-center gap-3"><CheckCircle2 className="h-5 w-5 text-emerald-700" /><div><div className="font-bold text-emerald-950">{screenshotAnalysis ? `Squad rated ${screenshotAnalysis.decision.rating?.grade ?? "provisionally"}` : team?.team_name}</div><div className="mt-0.5 text-xs text-emerald-800">{screenshotAnalysis ? "Screenshot squad detected · exact selling prices remain unavailable" : `Team ${parsedTeam?.teamId} verified`}</div></div></div></div>
          <h2 className="mt-6 text-xl font-black text-slate-950">How should recommendations feel?</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">Points maximization remains the core objective. These preferences control how the safe and aggressive alternatives are presented.</p>
          <ChoiceGroup label="Risk style" value={preferences.riskStyle} onChange={(riskStyle) => setPreferences((current) => ({ ...current, riskStyle }))} options={[{ value: "safe", title: "Safe", body: "Minutes security and lower downside." }, { value: "balanced", title: "Balanced", body: "Best default blend of points and risk." }, { value: "aggressive", title: "Aggressive", body: "More upside and variance." }]} />
          <ChoiceGroup label="Alternative picks" value={preferences.alternativeStyle} onChange={(alternativeStyle) => setPreferences((current) => ({ ...current, alternativeStyle }))} options={[{ value: "popular", title: "Popular", body: "Template alternatives first." }, { value: "differential", title: "Differential", body: "Lower-owned alternatives first." }, { value: "both", title: "Both", body: "Show one of each when useful." }]} />
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between"><button type="button" onClick={() => setStep(1)} className="inline-flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-bold text-slate-600 hover:bg-slate-100"><ArrowLeft className="h-4 w-4" />Back</button><button type="button" onClick={() => setStep(3)} className="sm-primary-button justify-center px-5 py-3">Continue<ArrowRight className="h-4 w-4" /></button></div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="mt-8">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-700"><Bell className="h-6 w-6" /></div>
          <h2 className="mt-5 text-xl font-black text-slate-950">Choose your reminders</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">Keep deadline guidance visible in the product. Email notifications are optional and can be changed later.</p>
          <div className="mt-6 space-y-3"><PreferenceToggle label="Deadline reminders" body="Show time-sensitive deadline prompts in SquadMetric." checked={preferences.deadlineReminders} onChange={(deadlineReminders) => setPreferences((current) => ({ ...current, deadlineReminders }))} /><PreferenceToggle label="Email notifications" body="Allow important deadline emails when notification delivery is enabled." checked={preferences.emailNotifications} onChange={(emailNotifications) => setPreferences((current) => ({ ...current, emailNotifications }))} /></div>
          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-violet-700" /><p className="text-xs leading-5 text-slate-600">{configured ? "Your team link and preferences will be stored under your authenticated account with row-level security." : "This local environment has no Supabase project configured, so setup will be saved only in this browser."}</p></div>
          <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between"><button type="button" onClick={() => setStep(2)} className="inline-flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-bold text-slate-600 hover:bg-slate-100"><ArrowLeft className="h-4 w-4" />Back</button><button type="button" onClick={finish} disabled={busy} className="sm-primary-button justify-center px-5 py-3 disabled:cursor-wait disabled:opacity-60">{busy ? "Saving…" : "Finish setup"}<ArrowRight className="h-4 w-4" /></button></div>
        </div>
      ) : null}

      {error ? <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900" role="alert">{error}</div> : null}
    </section>
  );
}

function ChoiceGroup<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (value: T) => void; options: Array<{ value: T; title: string; body: string }> }) {
  return <fieldset className="mt-6"><legend className="text-sm font-bold text-slate-800">{label}</legend><div className="mt-3 grid gap-3 sm:grid-cols-3">{options.map((option) => <label key={option.value} className={`cursor-pointer rounded-2xl border p-4 transition ${value === option.value ? "border-violet-500 bg-violet-50 ring-2 ring-violet-100" : "border-slate-200 hover:border-slate-300"}`}><input type="radio" name={label} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} className="sr-only" /><span className="block text-sm font-bold text-slate-950">{option.title}</span><span className="mt-1 block text-xs leading-5 text-slate-600">{option.body}</span></label>)}</div></fieldset>;
}

function PreferenceToggle({ label, body, checked, onChange }: { label: string; body: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex cursor-pointer items-center justify-between gap-5 rounded-2xl border border-slate-200 p-4"><span><span className="block text-sm font-bold text-slate-950">{label}</span><span className="mt-1 block text-xs leading-5 text-slate-600">{body}</span></span><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-5 w-5 accent-violet-600" /></label>;
}
