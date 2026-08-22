import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Terms of Use" };

export default function TermsPage() {
  return <LegalPage title="Terms of Use" intro="These terms govern your use of SquadMetric as an independent FPL analytics and recommendation service.">
    <Section title="Recommendations, not execution"><p>SquadMetric provides statistical estimates and decision support. It does not access your official FPL password, execute transfers, select captains, change your bench, or activate chips. You remain responsible for every official FPL action.</p></Section>
    <Section title="No guaranteed result"><p>Football outcomes, team news, lineups, fixture changes, and model uncertainty can make recommendations wrong. No score, rank, profit, availability, or top-1% finish is guaranteed.</p></Section>
    <Section title="Your account"><p>You must provide accurate signup information, protect your account, and link only public FPL identifiers you are entitled to use. Tell us promptly if you believe your account is compromised.</p></Section>
    <Section title="Acceptable use"><p>Do not abuse, disrupt, scrape at harmful scale, reverse engineer protected services, bypass security controls, impersonate others, or use SquadMetric unlawfully. We may restrict access needed to protect the service and other users.</p></Section>
    <Section title="Service changes"><p>FPL rules and source data change frequently. SquadMetric may change models, features, supported seasons, or availability to preserve correctness, security, or compliance.</p></Section>
    <Section title="Intellectual property and independence"><p>SquadMetric’s original software, design, and analysis remain protected. Premier League and Fantasy Premier League names and marks belong to their owners. SquadMetric is not affiliated with or endorsed by the Premier League.</p></Section>
    <Section title="Liability"><p>To the extent permitted by law, SquadMetric is provided without warranties and is not liable for decisions made from predictions, lost rank, missed deadlines, unavailable data, or indirect losses.</p></Section>
  </LegalPage>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) { return <section><h2 className="text-xl font-black text-slate-950">{title}</h2><div className="mt-3 space-y-3">{children}</div></section>; }
