"use client";

import { useState } from "react";
import { DemoBadge } from "@/components/DemoBadge";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricCard } from "@/components/MetricCard";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { SavedPortfolio } from "@/lib/portfolios";
import { useCompute } from "@/lib/useCompute";
import { PortfolioResults, portfolioCsvInput } from "./PortfolioResults";
import { PortfolioReturns } from "./PortfolioReturns";
import { PositionsTable } from "./PositionsTable";

/** Value metrics only the saved portfolio has (it knows quantities, cost prices and imported sells). */
const VALUE_METRICS = ["market_value", "cost_basis", "unrealized_pnl", "unrealized_return", "realized_pnl"] as const;
const SETTINGS = ["benchmark", "start", "end"] as const;
type Settings = Record<(typeof SETTINGS)[number], string>;

const DEFAULTS: Settings = { benchmark: "DEMO-MKT", start: "2021-01-01", end: "2025-12-31" };

/**
 * Performance, risk and value of one saved portfolio, from
 * `POST /portfolios/{id}/metrics`. Holdings are read server-side from the saved version.
 */
export function SavedPortfolioResults({ portfolio }: { portfolio: SavedPortfolio }) {
  const t = getMessages();
  const p = t.portfolio;
  const s = p.saved;
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const { result, fieldErrors, error } = useCompute<string, string>(`/portfolios/${portfolio.id}/metrics`, {
    benchmark: settings.benchmark.trim() || null,
    start: settings.start || null,
    end: settings.end || null,
  });
  const currency = String(result?.metrics["market_value:portfolio"]?.details?.currency ?? portfolio.holdings[0]?.currency ?? "");
  // Unknown tickers come back on their holding row; list them in the notice.
  const holdingErrors = Object.entries(fieldErrors)
    .filter(([field]) => field.startsWith("holdings."))
    .map(([, message]) => message);

  return (
    <section data-testid="saved-results" aria-label={s.sections.value} className="min-w-0 space-y-6">
      <div>
        <h3 className="text-sm font-medium">{s.analysisHeading}</h3>
        <div className="mt-2 grid gap-4 sm:grid-cols-3">
          {SETTINGS.map((field) => (
            <TextField
              key={field}
              type={field === "benchmark" ? "text" : "date"}
              name={`saved-${field}`}
              label={p.inputs[field].label}
              value={settings[field]}
              onChange={(value) => setSettings((v) => ({ ...v, [field]: value }))}
              error={fieldErrors[field]}
            />
          ))}
        </div>
      </div>
      <DemoBadge source={result?.source} />
      {error && (
        <ErrorNotice
          title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
          message={[error, ...holdingErrors].join(" ")}
        />
      )}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{s.sections.value}</h2>
          {result && (
            <ExportCsvButton
              label={s.sections.value}
              filename={csvFilename("portfolio", "value", portfolioCsvInput(result))}
              demo={result.source.is_demo}
              table={{
                columns: [t.common.csv.metric, t.common.csv.value, t.common.csv.currency],
                rows: VALUE_METRICS.map((id) => [
                  s.metrics[id].name,
                  result.metrics[`${id}:portfolio`],
                  id === "unrealized_return" ? null : currency,
                ]),
              }}
            />
          )}
        </div>
        <p className="mt-1 text-sm text-black/70 dark:text-white/70">{s.sections.valueNote}</p>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          {VALUE_METRICS.map((id) => (
            <MetricCard
              key={id}
              id={id}
              explainer={s.metrics[id]}
              values={[
                {
                  id: `${id}:portfolio`,
                  label: id === "unrealized_return" ? undefined : currency,
                  result: result?.metrics[`${id}:portfolio`],
                },
              ]}
            />
          ))}
        </div>
      </div>
      <div>
        <h2 className="text-lg font-semibold">{s.sections.positions}</h2>
        <div className="mt-2">
          <PositionsTable result={result} currency={currency} />
        </div>
      </div>
      <PortfolioReturns portfolioId={portfolio.id} start={settings.start} end={settings.end} />
      <PortfolioResults result={result} metricsNote={s.sections.metricsNote} />
    </section>
  );
}
