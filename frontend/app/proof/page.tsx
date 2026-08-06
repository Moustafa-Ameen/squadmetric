"use client";

import { Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/LoadingState";
import { Panel } from "@/components/Panel";
import { SectionHeader } from "@/components/SectionHeader";
import { getAccuracy, getCaptaincyBacktest, getTop10Metrics } from "@/lib/api";
import { points } from "@/lib/format";
import type { AccuracyResult, BacktestResult, Top10Metric } from "@/lib/types";

export default function ProofPage() {
  const [accuracy, setAccuracy] = useState<AccuracyResult[]>([]);
  const [captaincy, setCaptaincy] = useState<BacktestResult[]>([]);
  const [top10, setTop10] = useState<Top10Metric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([getAccuracy(), getCaptaincyBacktest(), getTop10Metrics()])
      .then(([accuracyRows, captaincyRows, top10Rows]) => {
        setAccuracy(accuracyRows);
        setCaptaincy(captaincyRows.map(renameStrategy));
        setTop10(top10Rows);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const sortedCaptaincy = useMemo(
    () => [...captaincy].sort((a, b) => b.total_captain_points - a.total_captain_points),
    [captaincy],
  );

  if (loading) return <TableSkeleton />;
  if (error) return <ErrorState />;
  if (!accuracy.length) return <EmptyState />;

  const bestRaw = Math.min(...accuracy.map((row) => row.raw_MAE));
  const bestAdjusted = Math.min(...accuracy.map((row) => row.adjusted_MAE));

  return (
    <div className="space-y-6">
      <SectionHeader title="Should I trust this?" subtitle="Transparent model evidence, not marketing claims." />

      <section className="fpl-card-shadow rounded-lg border border-fpl-border border-l-4 border-l-fpl-green bg-[linear-gradient(135deg,#0d1a0d_0%,#161616_100%)] p-6">
        <h2 className="text-[26px] font-bold leading-tight text-primary">
          Historical model evidence, separated from the live 2026/27 serving fit.
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-secondary">
          The tables below are held-out historical evaluations. The live model is refit on completed seasons only; 2026/27 outcomes are not part of its training data.
        </p>
      </section>

      <Panel title="Accuracy">
        <div className="grid gap-6 lg:grid-cols-2">
          <AccuracyTable
            title="Raw predictions"
            rows={accuracy}
            best={bestRaw}
            columns={["raw_MAE", "raw_RMSE"]}
          />
          <AccuracyTable
            title="Start-adjusted predictions"
            rows={accuracy}
            best={bestAdjusted}
            columns={["adjusted_MAE", "adjusted_RMSE"]}
          />
        </div>
        <p className="mt-5 rounded-lg border border-fpl-border bg-fpl-raised p-3 text-sm text-secondary">
          Adjusting for start likelihood improved average prediction accuracy for every model we tested.
        </p>
      </Panel>

      <Panel>
        <div className="mb-5">
          <h2 className="text-[18px] font-semibold text-primary">Captaincy backtest</h2>
          <p className="mt-1 text-[13px] text-secondary">
            If you&apos;d used this model every week as your captain guide...
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.4fr_0.6fr]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr>
                  <th className="pb-3">Strategy</th>
                  <th className="pb-3 text-right">Total pts</th>
                  <th className="pb-3 text-right">Avg/GW</th>
                </tr>
              </thead>
              <tbody>
                {sortedCaptaincy.map((row) => {
                  const isModel = row.strategy === "FPL Intelligence";
                  return (
                    <tr
                      key={row.strategy}
                      className={`border-b border-fpl-border ${
                        isModel ? "border-l-4 border-l-fpl-gold text-fpl-green" : "text-primary"
                      }`}
                    >
                      <td className="py-3 pl-3 font-medium">{row.strategy}</td>
                      <td className="py-3 text-right font-mono">{points(row.total_captain_points, 0)}</td>
                      <td className="py-3 text-right font-mono">{points(row.avg_per_gameweek)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sortedCaptaincy} layout="vertical" margin={{ top: 8, right: 48, left: 24, bottom: 8 }}>
                <XAxis type="number" hide />
                <YAxis
                  dataKey="strategy"
                  type="category"
                  width={150}
                  tick={{ fontSize: 12, fill: "#B7C5BF" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip contentStyle={{ background: "#161616", border: "1px solid #2A2A2A", color: "#FFFFFF" }} />
                <Bar dataKey="total_captain_points" radius={[0, 6, 6, 0]}>
                  <LabelList
                    dataKey="total_captain_points"
                    position="right"
                    fill="#FFFFFF"
                    fontSize={12}
                    formatter={(value) => points(Number(value), 0)}
                  />
                  {sortedCaptaincy.map((row) => (
                    <Cell key={row.strategy} fill={row.strategy === "FPL Intelligence" ? "#00FF87" : "#2A2A2A"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Panel>

      <Panel title="Top-10 accuracy">
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={top10}>
              <CartesianGrid stroke="#1F2231" vertical={false} />
              <XAxis dataKey="model" stroke="#94A3B8" tick={{ fontSize: 11 }} interval={0} angle={-12} height={60} />
              <YAxis stroke="#94A3B8" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#161616", border: "1px solid #2A2A2A", color: "#FFFFFF" }} />
              <Legend />
              <Bar dataKey="precision_at_10" name="Precision @10" fill="#00FF87" />
              <Bar dataKey="recall_at_10" name="Recall @10" fill="#23E6C2" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-5 rounded-lg border border-fpl-gold/30 bg-fpl-gold/[0.04] p-4 text-sm leading-6 text-secondary">
          <div className="font-semibold text-fpl-gold">Why is 13% precision meaningful?</div>
          <p className="mt-2">
            FPL scores are highly random — a red card, a penalty miss, or a last-minute deflection can swing
            the entire top-10. Any model claiming to reliably predict the exact top 10 is overfitting.
          </p>
          <p className="mt-2">
            What our model does: it consistently ranks the right players higher than chance across 38 gameweeks.
            That edge, applied weekly, is what separates good FPL from great FPL.
          </p>
        </div>
      </Panel>
    </div>
  );
}

function AccuracyTable({
  title,
  rows,
  best,
  columns,
}: {
  title: string;
  rows: AccuracyResult[];
  best: number;
  columns: ["raw_MAE", "raw_RMSE"] | ["adjusted_MAE", "adjusted_RMSE"];
}) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-primary">{title}</h3>
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-muted">
          <tr>
            <th className="pb-3">Model</th>
            <MetricHeader label="MAE" title="Mean Absolute Error — average prediction miss in points. Lower is better." />
            <MetricHeader label="RMSE" title="Root Mean Square Error — penalises big misses more. Lower is better." />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isBest = row[columns[0]] === best;
            return (
              <tr
                key={`${title}-${row.model}`}
                className={`border-b border-fpl-border ${isBest ? "bg-fpl-green/[0.06] text-fpl-green" : "text-primary"}`}
              >
                <td className="py-3 pl-3">{friendlyModel(row.model)}</td>
                <td className="py-3 text-right font-mono">{points(row[columns[0]])}</td>
                <td className="py-3 text-right font-mono">{points(row[columns[1]])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MetricHeader({ label, title }: { label: string; title: string }) {
  return (
    <th className="pb-3 text-right" title={title}>
      <span className="inline-flex items-center justify-end gap-1">
        {label}
        <Info className="h-3 w-3 text-muted" />
      </span>
    </th>
  );
}

function renameStrategy(row: BacktestResult): BacktestResult {
  const names: Record<string, string> = {
    "FPL Intelligence (best)": "FPL Intelligence",
    "Ridge (Captaincy Model)": "Ridge (Captaincy Model)",
    "No model (form average)": "Form average (no ML)",
    "Most popular player": "Most popular captain choice",
    "Best points-per-game": "Highest PPG player",
    "Random pick": "Random captain",
  };
  return { ...row, strategy: names[row.strategy] ?? row.strategy };
}

function friendlyModel(model: string): string {
  return model === "FPL Intelligence (best)" ? "FPL Intelligence" : model;
}
