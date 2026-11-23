"use client";

import { useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { MetricExplainer } from "@/components/MetricExplainer";
import { getMessages } from "@/i18n";
import type { MetricResult } from "@/lib/envelope";
import { formatValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import type { RiskSelection } from "./TechnicalAnalysis";

// Metric ids are "correlation:<row>:<column>", for every ordered pair (diagonal included).
type CorrelationId = `correlation:${string}:${string}`;

/** Blue for positive, red for negative correlation; opacity grows with |value|. */
function cellColor(result: MetricResult | undefined): string | undefined {
  if (result?.status !== "ok" || result.value === null) return undefined;
  const v = Math.max(-1, Math.min(1, result.value));
  return v >= 0 ? `rgba(37, 99, 235, ${v})` : `rgba(220, 38, 38, ${-v})`;
}

function cellText(result: MetricResult | undefined): string {
  if (!result) return "…";
  if (result.status !== "ok" || result.value === null) return "–";
  return formatValue(result.value, result.unit);
}

/** Hoverable correlation matrix of the selected tickers' (and the benchmark's) daily returns. */
export function CorrelationHeatmap({ selection }: { selection: RiskSelection }) {
  const t = getMessages().riskTechnical.heatmap;
  const common = getMessages().common;
  const { result, error } = useCompute<CorrelationId, string>("/risk/correlation", selection);
  const [hovered, setHovered] = useState<[string, string] | null>(null);

  const symbols = [...new Set([...selection.tickers, selection.benchmark])];
  const at = (a: string, b: string) => result?.metrics[`correlation:${a}:${b}`];
  const hoveredResult = hovered ? at(...hovered) : undefined;

  return (
    <div>
      <h2 className="text-lg font-semibold">{t.heading}</h2>
      {error && <ErrorNotice title={common.errors.heading} message={error} />}
      <div className="mt-2 max-w-full overflow-x-auto">
        <table aria-label={t.label} className="border-separate border-spacing-0.5 font-mono text-xs tabular-nums">
          <thead>
            <tr>
              <th scope="col" />
              {symbols.map((b) => (
                <th key={b} scope="col" className="px-1 pb-1 font-medium">
                  {b}
                </th>
              ))}
            </tr>
          </thead>
          <tbody onMouseLeave={() => setHovered(null)}>
            {symbols.map((a) => (
              <tr key={a}>
                <th scope="row" className="pr-2 text-right font-medium">
                  {a}
                </th>
                {symbols.map((b) => {
                  const r = at(a, b);
                  const strong = r?.status === "ok" && r.value !== null && Math.abs(r.value) > 0.6;
                  return (
                    <td
                      key={b}
                      tabIndex={0}
                      data-correlation={`${a}:${b}`}
                      data-status={r?.status}
                      aria-label={`${a} ${t.versus} ${b}: ${cellText(r)}`}
                      onMouseEnter={() => setHovered([a, b])}
                      onFocus={() => setHovered([a, b])}
                      onBlur={() => setHovered(null)}
                      className={`h-9 min-w-12 rounded-sm border border-black/10 px-1 text-center outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-white/10 ${
                        strong ? "text-white" : ""
                      }`}
                      style={{ background: cellColor(r) }}
                    >
                      {cellText(r)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p data-testid="heatmap-tooltip" role="status" className="mt-1 min-h-5 text-sm text-black/70 dark:text-white/70">
        {hovered &&
          `${hovered[0]} ${t.versus} ${hovered[1]}: ${
            hoveredResult?.status === "ok" || !hoveredResult ? cellText(hoveredResult) : hoveredResult.reason
          }`}
      </p>
      <MetricExplainer explainer={t.explainer} />
    </div>
  );
}
