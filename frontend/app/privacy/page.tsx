import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  return <LegalPage title="Privacy Policy" intro="This policy explains what SquadMetric stores, why it is needed, and the choices available to you.">
    <Section title="Information we use"><p>SquadMetric uses the public FPL Team ID you choose to link, verified public team information, preferences, saved drafts, watched players, and recommendation history to provide its features.</p><p>We do not ask for or store your official Fantasy Premier League password.</p></Section>
    <Section title="How we use information"><p>We use this information to personalize weekly recommendations and preserve your workspace in your browser. We do not sell personal information.</p></Section>
    <Section title="Local storage and cookies"><p>Your linked team, settings, drafts, watchlist, and decision history are stored locally in your browser. SquadMetric does not require an account and currently uses no advertising or behavioral analytics cookies.</p></Section>
    <Section title="Processors and retention"><p>The production hosts process ordinary web requests. Public FPL data is obtained from official public endpoints. Browser data remains on your device until you clear it or disconnect your team.</p></Section>
    <Section title="Your choices"><p>You can download your browser data or disconnect your public FPL Team ID from Settings at any time.</p></Section>
    <Section title="Contact"><p>{supportEmail ? <>Privacy questions can be sent to <a className="font-semibold text-violet-700 underline" href={`mailto:${supportEmail}`}>{supportEmail}</a>.</> : "A privacy contact address will be published before public launch."}</p></Section>
    <Section title="Independence"><p>SquadMetric is independent fantasy football analytics and is not affiliated with, sponsored by, or endorsed by the Premier League.</p></Section>
  </LegalPage>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) { return <section><h2 className="text-xl font-black text-slate-950">{title}</h2><div className="mt-3 space-y-3">{children}</div></section>; }
