export function FeedbackLink({ className }: { className?: string }) {
  const email = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  if (!email) return null;
  const subject = encodeURIComponent("SquadMetric feedback");
  return <a href={`mailto:${email}?subject=${subject}`} className={className}>Send feedback</a>;
}
