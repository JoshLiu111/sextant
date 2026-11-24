"use client";

import { DemoBadge } from "@/components/DemoBadge";
import { ErrorNotice } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { formatChartPercent, formatValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { FrontierChart, type MarkedPortfolio } from "./FrontierChart";
import { series } from "@/lib/chartColors";

/** Portfolios in `POST /portfolio/frontier`: metrics `<stat>:<who>` and `weight:<TICKER>:<who>`. */
const WHO = ["max_sharpe", "min_variance", "current"] as const;
type Who = (typeof WHO)[number];
const STATS = ["expected_return", "volatility", "sharpe"] as const;

const COLORS: Record<Who, string> = { max_sharpe: series(0), min_variance: series(1), current: series(2) };

type FrontierEnvelope = ResultEnvelope<string, string>;

function marked(result: FrontierEnvelope, labels: Record<Who, string>): MarkedPortfolio[] {
  return WHO.flatMap((who) => {
    const x = result.metrics[`volatility:${who}`];
    const y = result.metrics[`expected_return:${who}`];
    if (x?.status !== "ok" || y?.status !== "ok" || x.value === null || y.value === null) return [];
    return [{ id: who, label: labels[who], point: { x: x.value, y: y.value }, color: COLORS[who] }];
  });
}

function Cell({ id, result }: { id: string; result: MetricResult | undefined }) {
  const status = getMessages().common.status;
  return (
    <td data-metric-value={id} data-status={result?.status ?? "pending"} className="px-3 py-1.5 text-right tabular-nums">
      {!result ? (
        <span className="text-muted">{status.pending}</span>
      ) : result.status === "ok" && result.value !== null ? (
        formatValue(result.value, result.unit)
      ) : (
        <span title={result.reason ?? undefined} className="font-sans text-xs text-muted">
          {status[result.status === "ok" ? "error" : result.status]}
          {result.reason ? `: ${result.reason}` : ""}
        </span>
      )}
    </td>
  );
}

/**
 * Story 56: the long-only mean-variance frontier of the demo portfolio's holdings,
 * marking the maximum-Sharpe, minimum-variance and current portfolios, with their
 * weights. `portfolio` is the demo portfolio's request body.
 */
export function EfficientFrontier({ portfolio }: { portfolio: Record<string, unknown> }) {
  const t = getMessages();
  const f = t.portfolioConstruction.frontier;
  const { result, fieldErrors, error } = useCompute<string, string>("/portfolio/frontier", portfolio);
  // The inputs live in the demo form, so name what is wrong here rather than "fix the highlighted fields".
  const fieldMessages = [...new Set(Object.values(fieldErrors))].join(" ");
  const tickers = ((result?.meta.parameters as { holdings?: { ticker: string }[] } | undefined)?.holdings ?? []).map(
    (h) => h.ticker,
  );
  const line = result?.series.frontier;
  const frontier = line?.status === "ok" ? line.points.flatMap((p) => (p.y === null ? [] : [{ x: Number(p.x), y: p.y }])) : [];

  return (
    <section aria-labelledby="frontier-heading" className="min-w-0 space-y-4">
      <h2 id="frontier-heading" className="text-2xl">
        {f.heading}
      </h2>
      <p className="text-sm text-ink-2">{f.intro}</p>
      <DemoBadge source={result?.source} />
      {error && (
        <ErrorNotice
          title={fieldMessages ? t.common.errors.invalidHeading : t.common.errors.heading}
          message={fieldMessages || error}
        />
      )}
      {result && (
        <FrontierChart
          label={f.chart.label}
          frontier={frontier}
          frontierLabel={f.frontierLine}
          marked={marked(result, f.who)}
          xLabel={f.chart.x}
          yLabel={f.chart.y}
          format={formatChartPercent}
        />
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <caption className="text-left text-lg font-medium">
            {f.weightsHeading}
            <span className="block text-xs font-normal text-muted">{f.weightsCaption}</span>
          </caption>
          <thead>
            <tr className="border-b border-rule">
              <th scope="col" className="px-3 py-1.5 text-left font-medium">
                {f.tickerColumn}
              </th>
              {WHO.map((who) => (
                <th key={who} scope="col" className="px-3 py-1.5 text-right font-medium">
                  <span aria-hidden className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: COLORS[who] }} />
                  {f.who[who]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => (
              <tr key={ticker} className="border-b border-rule">
                <td className="px-3 py-1.5 tabular-nums">{ticker}</td>
                {WHO.map((who) => (
                  <Cell key={who} id={`weight:${ticker}:${who}`} result={result?.metrics[`weight:${ticker}:${who}`]} />
                ))}
              </tr>
            ))}
            {STATS.map((stat) => (
              <tr key={stat} className="border-b border-rule">
                <th scope="row" className="px-3 py-1.5 text-left font-medium">
                  {f.rows[stat]}
                </th>
                {WHO.map((who) => (
                  <Cell key={who} id={`${stat}:${who}`} result={result?.metrics[`${stat}:${who}`]} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">{f.method}</p>
    </section>
  );
}
