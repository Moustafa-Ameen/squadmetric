"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("SquadMetric route failed", error);
  }, [error]);

  return (
    <div className="rounded-3xl border border-rose-200 bg-white p-6 shadow-sm" role="alert">
      <div className="flex items-center gap-3 text-primary">
        <AlertTriangle className="h-5 w-5 text-rose-600" />
        <h1 className="text-lg font-semibold">This page could not load safely</h1>
      </div>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-secondary">
        SquadMetric will not show a recommendation from incomplete data. Retry the request;
        if it still fails, check the decision service status.
      </p>
      <button
        type="button"
        onClick={reset}
        className="sm-primary-button mt-5 px-4 py-2.5"
      >
        <RefreshCw className="h-4 w-4" />
        Retry
      </button>
    </div>
  );
}
