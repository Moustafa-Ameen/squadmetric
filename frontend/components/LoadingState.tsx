export function LoadingState() {
  return <div role="status" aria-label="Loading decision data"><CardGridSkeleton /></div>;
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading your gameweek dashboard">
      <div className="space-y-3"><div className="skeleton h-4 w-28" /><div className="skeleton h-10 w-80 max-w-full" /><div className="skeleton h-4 w-[430px] max-w-full" /></div>
      <div className="skeleton h-20 rounded-2xl" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.55fr)]"><div className="skeleton h-72 rounded-3xl" /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1"><div className="skeleton h-32 rounded-3xl" /><div className="skeleton h-32 rounded-3xl" /></div></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="skeleton h-44 rounded-3xl" />)}</div>
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-4">
      <div className="skeleton h-16 rounded-[10px] border border-fpl-border bg-fpl-card" />
      <div className="rounded-[10px] border border-fpl-border bg-fpl-card p-4">
        <div className="mb-4 grid grid-cols-[1.2fr_0.7fr_0.7fr_0.7fr] gap-4">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="skeleton h-4" />
          ))}
        </div>
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, index) => (
            <div key={index} className="grid grid-cols-[1.2fr_0.7fr_0.7fr_0.7fr] gap-4">
              <div className="skeleton h-9" />
              <div className="skeleton h-9" />
              <div className="skeleton h-9" />
              <div className="skeleton h-9" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function PitchSkeleton() {
  const rows = [1, 4, 4, 2];
  return (
    <div className="space-y-4">
      <div className="skeleton h-14 rounded-[10px] border border-fpl-border bg-fpl-card" />
      <div className="rounded-[10px] border border-fpl-border bg-[linear-gradient(180deg,#0d5c2e_0%,#0a4a25_50%,#0d5c2e_100%)] p-6">
        <div className="space-y-7">
          {rows.map((count, rowIndex) => (
            <div key={rowIndex} className="flex justify-center gap-5">
              {Array.from({ length: count }).map((_, index) => (
                <div key={index} className="flex w-[92px] flex-col items-center gap-2">
                  <div className="skeleton h-14 w-16" />
                  <div className="skeleton h-3 w-20" />
                  <div className="skeleton h-3 w-12" />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3 rounded-[10px] border border-fpl-border bg-fpl-card p-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="skeleton h-12" />
        ))}
      </div>
    </div>
  );
}

export function CardGridSkeleton({ cards = 6 }: { cards?: number }) {
  return (
    <div className="space-y-4">
      <div className="skeleton h-20 rounded-[10px] border border-fpl-border bg-fpl-card" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: cards }).map((_, index) => (
          <div key={index} className="rounded-[10px] border border-fpl-border bg-fpl-card p-4">
            <div className="skeleton h-5 w-2/3" />
            <div className="skeleton mt-3 h-4 w-full" />
            <div className="skeleton mt-2 h-4 w-4/5" />
            <div className="mt-5 grid grid-cols-3 gap-2">
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
              <div className="skeleton h-12" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function HeroSkeleton() {
  return (
    <div className="space-y-4">
      <div className="skeleton h-14 rounded-[10px] border border-fpl-border bg-fpl-card" />
      <div className="rounded-[10px] border border-fpl-border bg-fpl-card p-6">
        <div className="grid gap-5 md:grid-cols-[96px_minmax(0,1fr)_160px] md:items-center">
          <div className="skeleton h-20 w-20" />
          <div>
            <div className="skeleton h-4 w-40" />
            <div className="skeleton mt-4 h-9 w-72 max-w-full" />
            <div className="skeleton mt-3 h-4 w-44" />
            <div className="skeleton mt-5 h-4 w-full" />
            <div className="skeleton mt-2 h-4 w-3/4" />
          </div>
          <div className="space-y-3">
            <div className="skeleton h-14" />
            <div className="skeleton h-6" />
          </div>
        </div>
      </div>
      <TableSkeleton rows={5} />
    </div>
  );
}

export function PlannerSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading planner data">
      <div className="skeleton h-16 rounded-[10px] border border-fpl-border bg-fpl-card" />
      <div className="rounded-[10px] border border-fpl-border bg-fpl-card p-4">
        <div className="mb-4 flex gap-2">
          {[3, 5, 8].map((item) => <div key={item} className="skeleton h-8 w-16" />)}
        </div>
        <div className="grid gap-2 md:grid-cols-5">
          {[0, 1, 2, 3, 4].map((item) => (
            <div key={item} className="skeleton h-24" />
          ))}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-[10px] border border-fpl-border bg-fpl-card p-5">
          <div className="skeleton h-5 w-48" />
          <div className="mt-4 space-y-3">
            {[0, 1, 2, 3, 4].map((item) => <div key={item} className="skeleton h-14" />)}
          </div>
        </div>
        <div className="rounded-[10px] border border-fpl-border bg-fpl-card p-5">
          <div className="skeleton h-5 w-40" />
          <div className="mt-4 space-y-3">
            {[0, 1, 2].map((item) => <div key={item} className="skeleton h-10" />)}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ErrorState() {
  return (
    <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800">
      This section could not load. Retry shortly; if the problem continues, check the SquadMetric data service.
    </div>
  );
}

export function EmptyState() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
      No recommendations are available yet. Complete team setup or return after the next data refresh.
    </div>
  );
}
