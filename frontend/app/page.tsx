import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  BellRing,
  Check,
  ChevronRight,
  CircleGauge,
  Crown,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import { Brand } from "@/components/Brand";
import { PublicHeader } from "@/components/PublicHeader";
import { PublicFooter } from "@/components/PublicFooter";

export const metadata: Metadata = {
  title: "SquadMetric — Smarter FPL Decisions",
};

const decisions = [
  { icon: RefreshCw, label: "Transfers", value: "Roll the transfer", detail: "Build flexibility for next week" },
  { icon: Crown, label: "Captain", value: "Haaland", detail: "Highest expected-points ceiling" },
  { icon: Users, label: "Bench", value: "Start your safest XI", detail: "Autosub protection included" },
  { icon: Zap, label: "Chip", value: "Save", detail: "No strong opportunity this week" },
];

export default function LandingPage() {
  return (
    <div className="marketing-page min-h-screen">
      <PublicHeader />
      <main id="main-content">
        <section className="relative overflow-hidden px-5 pb-20 pt-16 sm:px-8 lg:px-10 lg:pb-28 lg:pt-24">
          <div className="marketing-orb marketing-orb-one" />
          <div className="marketing-orb marketing-orb-two" />
          <div className="relative mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[minmax(0,0.92fr)_minmax(520px,1.08fr)]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800">
                <Sparkles className="h-3.5 w-3.5" />
                Built for the 2026/27 season
              </div>
              <h1 className="mt-7 max-w-3xl text-5xl font-black tracking-[-0.055em] text-slate-950 sm:text-6xl lg:text-[72px] lg:leading-[0.98]">
                Make the smarter FPL decision.
                <span className="brand-gradient block">Every gameweek.</span>
              </h1>
              <p className="mt-7 max-w-xl text-lg leading-8 text-slate-600">
                SquadMetric turns projections, fixtures, availability, and uncertainty into one clear weekly plan for your transfers, captain, bench, and chips.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link href="/signup" className="sm-primary-button justify-center px-6 py-3.5">
                  Create your account
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link href="/login" className="sm-secondary-button justify-center px-6 py-3.5">
                  Sign in
                </Link>
              </div>
              <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-slate-600">
                {["Clear weekly actions", "Confidence-aware alternatives", "No FPL password required"].map((item) => (
                  <span key={item} className="flex items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                      <Check className="h-3 w-3" />
                    </span>
                    {item}
                  </span>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="dashboard-preview">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4 sm:px-6">
                  <Brand compact />
                  <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-bold text-violet-700">Example weekly plan</span>
                </div>
                <div className="p-5 sm:p-6">
                  <div className="rounded-2xl bg-slate-950 p-5 text-white sm:p-6">
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-xs font-bold uppercase tracking-[0.15em] text-emerald-300">Primary recommendation</span>
                      <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">High confidence</span>
                    </div>
                    <h2 className="mt-4 text-2xl font-bold">Roll the free transfer</h2>
                    <p className="mt-2 max-w-lg text-sm leading-6 text-slate-300">
                      The immediate upgrade is marginal. Keeping two transfers creates a stronger route next gameweek.
                    </p>
                    <div className="mt-5 flex items-center gap-3 text-sm font-semibold text-emerald-300">
                      View the reasoning <ChevronRight className="h-4 w-4" />
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {decisions.map(({ icon: Icon, label, value, detail }) => (
                      <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.11em] text-slate-500">
                          <Icon className="h-4 w-4 text-violet-600" /> {label}
                        </div>
                        <div className="mt-3 font-bold text-slate-950">{value}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="absolute -bottom-5 -left-5 hidden rounded-2xl border border-emerald-200 bg-white px-4 py-3 shadow-xl sm:block">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700"><CircleGauge className="h-5 w-5" /></span>
                  <div><div className="text-xs text-slate-500">Decision confidence</div><div className="font-bold text-slate-950">74% · Balanced</div></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="how-it-works" className="border-y border-slate-200 bg-white px-5 py-20 sm:px-8 lg:px-10">
          <div className="mx-auto max-w-7xl">
            <div className="max-w-2xl">
              <div className="text-sm font-bold uppercase tracking-[0.16em] text-violet-700">One plan, not more noise</div>
              <h2 className="mt-4 text-3xl font-black tracking-[-0.035em] text-slate-950 sm:text-4xl">Everything important, in the order you need it.</h2>
              <p className="mt-4 text-base leading-7 text-slate-600">Start with the recommendation. Open the evidence only when you want the detail.</p>
            </div>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {[
                { icon: ShieldCheck, number: "01", title: "Link your team", body: "Use a public FPL Team ID or team URL. Your FPL login stays private." },
                { icon: BarChart3, number: "02", title: "Review your plan", body: "See one primary recommendation plus safer and more aggressive alternatives." },
                { icon: BellRing, number: "03", title: "Act before the deadline", body: "Check transfers, captaincy, bench order, and chip decisions in one place." },
              ].map(({ icon: Icon, number, title, body }) => (
                <article key={number} className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                  <div className="flex items-center justify-between"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-100 text-violet-700"><Icon className="h-5 w-5" /></span><span className="text-xs font-black text-slate-600">{number}</span></div>
                  <h3 className="mt-7 text-lg font-bold text-slate-950">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="px-5 py-20 sm:px-8 lg:px-10">
          <div className="mx-auto max-w-7xl rounded-[32px] bg-slate-950 px-6 py-12 text-center text-white sm:px-10">
            <h2 className="text-3xl font-black tracking-[-0.035em] sm:text-4xl">Your next gameweek starts with one clear plan.</h2>
            <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-300">Set up your SquadMetric account now. Team linking and personalized recommendations follow in the guided onboarding flow.</p>
            <Link href="/signup" className="sm-primary-button mt-8 justify-center px-6 py-3.5">Get started <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
