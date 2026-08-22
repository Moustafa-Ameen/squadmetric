import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  return <LegalPage title="Privacy Policy" intro="This policy explains what SquadMetric stores, why it is needed, and the choices available to you.">
    <Section title="Information we collect"><p>When accounts are enabled, Supabase processes your email address, authentication identity, and session information. We store the public FPL Team ID you choose to link, verified public team information, preferences, saved drafts, watched players, recommendation snapshots, and whether you accepted or rejected a recommendation.</p><p>We do not ask for or store your official Fantasy Premier League password.</p></Section>
    <Section title="How we use information"><p>We use this information to authenticate you, synchronize your workspace across devices, personalize weekly recommendations, preserve your own decision history, maintain security, and diagnose reliability problems. We do not sell personal information.</p></Section>
    <Section title="Local storage and cookies"><p>SquadMetric uses strictly necessary authentication cookies and browser storage for account sessions, team settings, drafts, display preferences, and resilient local operation. No advertising or behavioral analytics cookies are currently used.</p></Section>
    <Section title="Processors and retention"><p>Supabase provides authentication and account storage. The production host may use Vercel for the website. Public FPL data is obtained from official public endpoints. We retain account data until you delete it, subject to limited security backups and legal obligations maintained by processors.</p></Section>
    <Section title="Your choices"><p>You can download your account data or permanently delete your account from Settings. You may disconnect your public FPL Team ID without deleting your SquadMetric account.</p></Section>
    <Section title="Contact"><p>{supportEmail ? <>Privacy questions can be sent to <a className="font-semibold text-violet-700 underline" href={`mailto:${supportEmail}`}>{supportEmail}</a>.</> : "A privacy contact address will be published before public launch."}</p></Section>
    <Section title="Independence"><p>SquadMetric is independent fantasy football analytics and is not affiliated with, sponsored by, or endorsed by the Premier League.</p></Section>
  </LegalPage>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) { return <section><h2 className="text-xl font-black text-slate-950">{title}</h2><div className="mt-3 space-y-3">{children}</div></section>; }
