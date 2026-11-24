"use client";

import { useState } from "react";
import { Histogram } from "@/components/Histogram";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import type { ResultEnvelope } from "@/lib/envelope";
import { formatChartPercent } from "@/lib/format";
import type { ReturnPeriod } from "./TimescaleInputs";

// Metric ids "skewness:<ticker>", "excess_kurtosis:<ticker>"; series "return_distribution:<ticker>"
// (x = bin center as a decimal return, y = count; details.bin_width, details.observations).
const SHAPE_METRICS = ["skewness", "excess_kurtosis"] as const;

export function ReturnDistribution({
  result,
  symbols,
  label,
  period,
}: {
  result: ResultEnvelope;
  symbols: string[];
  label: (ticker: string) => string;
  period: ReturnPeriod;
}) {
  const ts = getMessages().risk.timescale;
  const d = ts.distribution;
  const adjective = ts.periods[period].label.toLowerCase();
  const [choice, setChoice] = useState<string | null>(null);
  const selected = choice && symbols.includes(choice) ? choice : symbols[0];
  const hist = selected ? result.series[`return_distribution:${selected}`] : undefined;
  const binWidth = typeof hist?.details.bin_width === "number" ? hist.details.bin_width : 0;
  const observations = typeof hist?.details.observations === "number" ? hist.details.observations : 0;

  return (
    <section aria-labelledby="risk-distribution" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="risk-distribution" className="text-xl">
          {d.heading}
        </h2>
        {symbols.length > 0 && (
          <label className="text-sm">
            <span className="mr-2">{d.select}</span>
            <select
              value={selected}
              onChange={(e) => setChoice(e.target.value)}
              className="rounded-card border border-muted px-2 py-1 tabular-nums"
            >
              {symbols.map((ticker) => (
                <option key={ticker} value={ticker}>
                  {label(ticker)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {SHAPE_METRICS.map((id) => (
          <MetricCard
            key={id}
            id={id}
            explainer={d.metrics[id]}
            values={symbols.map((ticker) => ({
              id: `${id}:${ticker}`,
              label: label(ticker),
              result: result.metrics[`${id}:${ticker}`],
            }))}
          />
        ))}
      </div>
      {hist?.status === "ok" ? (
        <div>
          <Histogram
            label={d.label}
            bins={hist.points.map((p) => ({ x: Number(p.x), count: p.y ?? 0 }))}
            binWidth={binWidth}
            xLabel={d.x}
            formatX={formatChartPercent}
            formatCount={(n) => d.count(n, adjective)}
          />
          <p data-testid="distribution-summary" className="mt-1 text-sm text-ink-2">
            {selected}: {d.summary(observations, adjective, formatChartPercent(binWidth))}
          </p>
        </div>
      ) : (
        hist && <p className="text-sm text-muted">{hist.reason}</p>
      )}
    </section>
  );
}
