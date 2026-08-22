export default function Loading() {
  return (
    <div className="space-y-5" role="status" aria-label="Loading decision data">
      <div className="h-36 animate-pulse rounded-xl border border-fpl-border bg-fpl-card" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div
            key={index}
            className="h-24 animate-pulse rounded-lg border border-fpl-border bg-fpl-card"
          />
        ))}
      </div>
      <div className="h-80 animate-pulse rounded-xl border border-fpl-border bg-fpl-card" />
    </div>
  );
}
