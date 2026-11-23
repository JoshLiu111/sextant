"use client";

import { LineChart, type ChartSeries } from "@/components/LineChart";
import { getMessages } from "@/i18n";
import type { ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartNumber, formatChartPercent } from "@/lib/format";

// Series ids "<chart>:<ticker>" from POST /risk/metrics; details.window = window in trading days.
const CHARTS = [
  { id: "rolling_volatility", formatY: formatChartPercent },
  { id: "rolling_sharpe", formatY: formatChartNumber },
  { id: "rolling_beta", formatY: formatChartNumber },
] as const;

/** One color per ticker, in the order the tickers were entered; the benchmark is grey. */
export const TICKER_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea", "#ea580c"];

function points(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

export function RollingCharts({
  result,
  symbols,
  benchmark,
  label,
}: {
  result: ResultEnvelope;
  symbols: string[];
  benchmark: string;
  label: (ticker: string) => string;
}) {
  const r = getMessages().risk.timescale.rolling;
  const window = symbols
    .map((t) => result.series[`rolling_volatility:${t}`])
    .find((s) => s?.status === "ok")?.details.window;

  return (
    <section aria-labelledby="risk-rolling" className="space-y-4">
      <div>
        <h2 id="risk-rolling" className="text-lg font-semibold">
          {r.heading}
        </h2>
        {typeof window === "number" && (
          <p data-testid="rolling-window-note" className="mt-1 text-sm text-black/70 dark:text-white/70">
            {r.windowNote(window)}
          </p>
        )}
      </div>
      {CHARTS.map((chart) => {
        const series: ChartSeries[] = symbols.map((ticker, i) => ({
          id: ticker,
          label: label(ticker),
          points: points(result.series[`${chart.id}:${ticker}`]),
          color: ticker === benchmark ? "#64748b" : TICKER_COLORS[i % TICKER_COLORS.length],
          dashed: ticker === benchmark,
        }));
        const reasons = symbols.flatMap((ticker) => {
          const s = result.series[`${chart.id}:${ticker}`];
          return s && s.status !== "ok" ? [`${ticker}: ${s.reason}`] : [];
        });
        return (
          <div key={chart.id} data-rolling-chart={chart.id}>
            <h3 className="text-sm font-medium text-black/70 dark:text-white/70">{r.charts[chart.id].name}</h3>
            <LineChart
              label={r.charts[chart.id].label}
              series={series}
              xLabel={r.x}
              formatX={formatChartDate}
              formatY={chart.formatY}
              height={220}
            />
            {reasons.length > 0 && (
              <p className="text-sm text-black/60 dark:text-white/60">{reasons.join(" ")}</p>
            )}
          </div>
        );
      })}
    </section>
  );
}
