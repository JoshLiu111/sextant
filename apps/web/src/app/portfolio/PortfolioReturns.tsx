"use client";

import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { PriceSource } from "@/lib/myData";
import { useCompute } from "@/lib/useCompute";

const RETURN_METRICS = ["twr", "twr_annualized", "irr"] as const;
type ReturnMetricId = `${(typeof RETURN_METRICS)[number]}:portfolio`;

/**
 * Time-weighted and money-weighted (IRR) returns of a saved portfolio over a date
 * range, from `POST /portfolios/{id}/returns` (holdings plus imported transactions).
 * Errors (bad range, unknown ticker) are shown by the surrounding results, which
 * send the same dates.
 */
export function PortfolioReturns({
  portfolioId,
  name,
  source,
  start,
  end,
  reportingCurrency,
}: {
  portfolioId: string;
  name: string;
  source: PriceSource;
  start: string;
  end: string;
  /** Values and trades in other currencies convert into this one; null: the first holding's. */
  reportingCurrency: string | null;
}) {
  const t = getMessages();
  const r = t.portfolio.saved.returns;
  const { result } = useCompute<ReturnMetricId, never>(`/portfolios/${portfolioId}/returns`, {
    source,
    start: start || null,
    end: end || null,
    reporting_currency: reportingCurrency,
  });

  return (
    <section aria-label={r.heading} data-testid="portfolio-returns">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{r.heading}</h2>
        {result && (
          <ExportCsvButton
            label={r.heading}
            filename={csvFilename("portfolio", "returns", name)}
            demo={result.source.is_demo}
            table={{
              columns: [t.common.csv.metric, t.common.csv.value],
              rows: RETURN_METRICS.map((id) => [r.metrics[id].name, result.metrics[`${id}:portfolio`]]),
            }}
          />
        )}
      </div>
      <p className="mt-1 text-sm text-black/70 dark:text-white/70">{r.note}</p>
      <div className="mt-2 grid gap-4 sm:grid-cols-3">
        {RETURN_METRICS.map((id) => (
          <MetricCard
            key={id}
            id={id}
            explainer={r.metrics[id]}
            values={[{ id: `${id}:portfolio`, result: result?.metrics[`${id}:portfolio`] }]}
          />
        ))}
      </div>
      <div className="mt-3 rounded-lg bg-black/[0.03] p-3 text-sm dark:bg-white/[0.05]">
        <h3 className="font-medium">{r.whichHeading}</h3>
        <p className="mt-1 text-black/80 dark:text-white/80">{r.which}</p>
      </div>
    </section>
  );
}
