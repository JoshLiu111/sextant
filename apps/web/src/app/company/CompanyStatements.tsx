"use client";

import { useState, type FormEvent } from "react";
import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricExplainer } from "@/components/MetricExplainer";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { csvFilename, type CsvTable } from "@/lib/csv";
import { formatStatementValue } from "@/lib/format";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { useFrequency } from "./FrequencyToggle";

// Mirrors StatementsEnvelope in apps/compute/sextant_compute/company/api.py.
// Cells are metrics "<item id>:<period id>"; the period id is its end date.
// Periods are fiscal years, or fiscal quarters (fiscal_quarter 1..4) with ?frequency=quarterly.
type Statement = "income" | "balance" | "cash_flow";
type Period = {
  id: string;
  label: string;
  fiscal_year: number;
  fiscal_quarter: number | null;
  start: string | null;
  end: string;
  filed: string;
  form: string;
  accession: string;
  url: string;
};
type Item = { id: string; label: string; statement: Statement; unit: string; display: boolean };
type StatementsResult = ResultEnvelope & {
  company: { ticker: string; cik: number; name: string };
  periods: Period[];
  items: Item[];
};

const STATEMENTS: Statement[] = ["income", "balance", "cash_flow"];
const DEFAULT_TICKER = "AAPL";
// Shareable links: `/company?ticker=MSFT` (the screener links here too).
const URL_CODEC = fieldsCodec({ ticker: DEFAULT_TICKER });

function Cell({ id, label, result }: { id: string; label: string; result: MetricResult | undefined }) {
  const c = getMessages().company;
  if (!result) return <span className="text-muted">…</span>;
  if (result.status !== "ok" || result.value === null) {
    return (
      <span
        data-metric-value={id}
        data-status={result.status}
        title={result.reason ?? `${label}: ${c.notReported}`}
        className="text-xs italic text-muted"
      >
        {c.notReported}
      </span>
    );
  }
  const d = result.details;
  const source = `${label} · ${c.sourceFiling}: ${d.form} ${c.filed} ${d.filed}${d.derived_from ? ` (${c.derived}: ${d.derived_from})` : ""}`;
  return (
    <a
      href={String(d.url)}
      target="_blank"
      rel="noreferrer"
      data-metric-value={id}
      data-status="ok"
      title={source}
      className="tabular-nums hover:underline"
    >
      {formatStatementValue(result.value, result.unit)}
    </a>
  );
}

function StatementTable({ statement, result }: { statement: Statement; result: StatementsResult }) {
  const c = getMessages().company;
  const items = result.items.filter((i) => i.statement === statement && i.display);
  const headingId = `statement-${statement}`;
  const csv: CsvTable = {
    columns: [c.lineItem, ...result.periods.map((p) => `${p.label} (${p.end})`)],
    rows: items.map((item) => [item.label, ...result.periods.map((p) => result.metrics[`${item.id}:${p.id}`])]),
  };
  return (
    <section aria-labelledby={headingId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="text-lg">
          {c.statements[statement]}
        </h3>
        <ExportCsvButton
          table={csv}
          label={c.statements[statement]}
          filename={csvFilename("company", c.statements[statement], result.company.ticker)}
          demo={result.source.is_demo}
        />
      </div>
      <div className="mt-2 overflow-x-auto rounded-card border border-rule">
        <table aria-labelledby={headingId} className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-rule align-bottom">
              <th scope="col" className="sticky left-0 bg-paper px-3 py-2 text-left font-medium">
                {c.lineItem}
              </th>
              {result.periods.map((p) => (
                <th key={p.id} scope="col" className="px-3 py-2 text-right font-medium">
                  <span className="block">{p.label}</span>
                  <span className="block text-xs font-normal text-muted">
                    {p.fiscal_quarter ? c.quarterEnded : c.yearEnded} {p.end}
                  </span>
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-xs font-normal text-muted underline decoration-dotted"
                  >
                    {p.form} {c.filed} {p.filed}
                  </a>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b border-rule last:border-0">
                <th
                  scope="row"
                  className="sticky left-0 bg-paper px-3 py-1.5 text-left font-normal"
                >
                  {item.label}
                </th>
                {result.periods.map((p) => {
                  const id = `${item.id}:${p.id}`;
                  return (
                    <td key={p.id} className="px-3 py-1.5 text-right">
                      <Cell id={id} label={item.label} result={result.metrics[id]} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function CompanyStatements() {
  const t = getMessages();
  const c = t.company;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const initialTicker = initial.ticker.trim().toUpperCase() || DEFAULT_TICKER;
  const [ticker, setTicker] = useState(initialTicker);
  const frequency = useFrequency();
  // Only a submitted ticker is fetched: typing doesn't fire EDGAR requests.
  const [query, setQuery] = useState({ ticker: initialTicker });
  const { result, fieldErrors, error, pending, run } = useCompute("/company/statements", { ...query, frequency });
  const statements = result as StatementsResult | null;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next = { ticker: ticker.trim() };
    share({ ticker: next.ticker.toUpperCase() });
    if (next.ticker === query.ticker) run();
    else setQuery(next);
  }

  return (
    <div className="mt-6 space-y-6">
      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby="company-inputs"
        className="flex flex-wrap items-end gap-4"
      >
        <h2 id="company-inputs" className="sr-only">
          {c.inputsHeading}
        </h2>
        <div className="w-full max-w-xs">
          <TextField
            name="ticker"
            label={c.inputs.ticker.label}
            hint={c.inputs.ticker.hint}
            value={ticker}
            onChange={setTicker}
            error={fieldErrors.ticker}
          />
        </div>
        <button
          type="submit"
          className="btn btn-primary mb-6"
        >
          {c.submit}
        </button>
      </form>

      <section data-testid="results" aria-label="Results" aria-busy={pending} className="min-w-0 space-y-6">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {statements ? (
          <>
            <div>
              <h2 className="text-xl">{statements.company.name}</h2>
              <p className="text-sm text-muted">
                {statements.company.ticker} · CIK {statements.company.cik} · {c.unitsNote}
              </p>
              {statements.periods.some((p) => p.fiscal_quarter) && (
                <p className="mt-1 text-xs text-muted">{c.quarterlyNote}</p>
              )}
              <MetricExplainer explainer={c.explainer} />
            </div>
            {STATEMENTS.map((s) => (
              <StatementTable key={s} statement={s} result={statements} />
            ))}
            <CalculationInfo result={statements} />
            <AiExplain tool="company" result={statements} />
          </>
        ) : (
          !error && <p className="text-sm text-muted">{c.loading}</p>
        )}
      </section>
    </div>
  );
}
