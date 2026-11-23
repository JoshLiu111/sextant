"use client";

import { CalculationInfo } from "@/components/CalculationInfo";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import type { ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartPercent } from "@/lib/format";

/** The P3 metric set, scored for the portfolio and the benchmark. Explainers are shared with Risk & Performance. */
const METRICS = [
  "annualized_return",
  "annualized_volatility",
  "max_drawdown",
  "var",
  "cvar",
  "sharpe",
  "sortino",
  "beta",
] as const;

/** Envelope ids: metrics `<metric>:<who>`, series `cumulative_return:<who>`. */
const WHO = ["portfolio", "benchmark"] as const;

export type PortfolioEnvelope = ResultEnvelope<string, string>;

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/**
 * The performance and risk view of one portfolio result from `POST /portfolio/metrics`:
 * cumulative return vs the benchmark and the risk metric cards. Shared by the demo
 * portfolio and (later) saved portfolios.
 */
export function PortfolioResults({ result }: { result: PortfolioEnvelope | null }) {
  const t = getMessages();
  const p = t.portfolio;
  const benchmark = (result?.meta.parameters as { benchmark?: string } | undefined)?.benchmark ?? "";
  const labels = { portfolio: p.portfolioLabel, benchmark: `${benchmark} ${p.benchmarkSuffix}` };
  const chartSeries: ChartSeries[] = result
    ? [
        {
          id: "portfolio",
          label: labels.portfolio,
          points: chartPoints(result.series["cumulative_return:portfolio"]),
          color: "#2563eb",
        },
        {
          id: "benchmark",
          label: labels.benchmark,
          points: chartPoints(result.series["cumulative_return:benchmark"]),
          color: "#64748b",
          dashed: true,
        },
      ]
    : [];

  return (
    <>
      <div>
        <h2 className="text-lg font-semibold">{p.sections.chart}</h2>
        <div className="mt-2">
          {result && (
            <LineChart
              label={p.chart.label}
              series={chartSeries}
              xLabel={p.chart.x}
              formatX={formatChartDate}
              formatY={formatChartPercent}
            />
          )}
        </div>
      </div>
      <div>
        <h2 className="text-lg font-semibold">{p.sections.metrics}</h2>
        <p className="mt-1 text-sm text-black/70 dark:text-white/70">{p.sections.metricsNote}</p>
        <div className="mt-2 grid gap-4 xl:grid-cols-3">
          {METRICS.map((id) => (
            <MetricCard
              key={id}
              id={id}
              explainer={t.risk.metrics[id]}
              values={WHO.map((who) => ({
                id: `${id}:${who}`,
                label: result ? labels[who] : undefined,
                result: result?.metrics[`${id}:${who}`],
              }))}
            />
          ))}
        </div>
      </div>
      {result && <CalculationInfo result={result} />}
    </>
  );
}
