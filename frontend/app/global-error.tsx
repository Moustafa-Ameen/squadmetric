"use client";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="en">
      <body className="bg-slate-100 p-8 text-slate-950">
        <main className="mx-auto max-w-xl rounded-3xl border border-rose-200 bg-white p-6 shadow-lg">
          <h1 className="text-xl font-semibold">SquadMetric could not start</h1>
          <p className="mt-3 text-sm text-slate-600">
            Recommendations are hidden until the application can load complete decision data.
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-5 rounded-xl bg-violet-700 px-4 py-2.5 font-bold text-white"
          >
            Retry
          </button>
        </main>
      </body>
    </html>
  );
}
