"use client";

import { ArrowRight, ShieldCheck, Trophy } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { getTeam } from "@/lib/api";
import {
  DEFAULT_ONBOARDING_PREFERENCES,
  persistOnboarding,
  persistProvisionalOnboarding,
} from "@/lib/account";
import { parseFplTeamInput } from "@/lib/fplTeam";
import type { ScreenshotAnalysis } from "@/lib/types";
import { ScreenshotTeamImport } from "./ScreenshotTeamImport";

export function OnboardingFlow() {
  const router = useRouter();
  const [teamInput, setTeamInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
      await getTeam(parsed.value.teamId);
      await persistOnboarding({
        teamId: parsed.value.teamId,
        preferences: DEFAULT_ONBOARDING_PREFERENCES,
      });
      router.replace("/dashboard");
      router.refresh();
    } catch {
      setError("We could not verify that team with the official FPL data service. Check the ID and try again.");
      setBusy(false);
    }
  }

  async function handleScreenshot(analysis: ScreenshotAnalysis) {
    setBusy(true);
    setError("");
    try {
      await persistProvisionalOnboarding({
        analysis,
        preferences: DEFAULT_ONBOARDING_PREFERENCES,
      });
      router.replace("/dashboard");
      router.refresh();
    } catch {
      setError("We read the screenshot but could not save it in this browser. Please try again.");
      setBusy(false);
    }
  }

  return (
    <section className="w-full max-w-2xl rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_rgba(15,23,42,0.12)] sm:p-8" aria-labelledby="onboarding-title">
      <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800">
        <ShieldCheck className="h-3.5 w-3.5" />
        No account needed
      </div>
      <div className="mt-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-700">
        <Trophy className="h-6 w-6" />
      </div>
      <h1 id="onboarding-title" className="mt-5 text-3xl font-black tracking-[-0.04em] text-slate-950">
        Rate your FPL team
      </h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Paste your Team ID or any official team URL. SquadMetric uses public FPL data and remembers the team only in this browser.
      </p>

      <form onSubmit={verifyTeam} className="mt-7">
        <label htmlFor="fpl-team-input" className="block text-sm font-bold text-slate-800">FPL Team ID or URL</label>
        <input
          id="fpl-team-input"
          value={teamInput}
          onChange={(event) => setTeamInput(event.target.value)}
          placeholder="123456 or fantasy.premierleague.com/en/entry/123456/event/4"
          className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-950 outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-100"
          aria-describedby="team-input-help"
        />
        <p id="team-input-help" className="mt-2 text-xs leading-5 text-slate-500">
          Numeric IDs and official links—including localized `/en/` links—are accepted. Your FPL password is never requested.
        </p>
        <button type="submit" disabled={!teamInput.trim() || busy} className="sm-primary-button mt-6 w-full justify-center px-5 py-3.5 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">
          {busy ? "Checking your team…" : "Rate my team"}<ArrowRight className="h-4 w-4" />
        </button>
      </form>

      <div className="my-6 flex items-center gap-3"><span className="h-px flex-1 bg-slate-200" /><span className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">or</span><span className="h-px flex-1 bg-slate-200" /></div>
      <ScreenshotTeamImport onAnalyzed={(analysis) => void handleScreenshot(analysis)} />

      <p className="mt-5 text-center text-xs leading-5 text-slate-500">
        Browser-only storage means there is no signup, password, or cloud account to manage.
      </p>
      {error ? <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900" role="alert">{error}</div> : null}
    </section>
  );
}
