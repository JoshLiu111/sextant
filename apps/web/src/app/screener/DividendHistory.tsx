"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { ResultEnvelope } from "@/lib/envelope";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";

// Mirrors DividendsEnvelope in apps/compute/sextant_compute/screener/calendar.py.
type DividendPeriod = {
  kind: "quarter" | "year";
  label: string;
  fiscal_year: number;
  start: string;
  end: string;
  value: number;
  derived: boolean;
  tag: string;
  filing: { form: string; filed: string; accession: string; url: string };
};
type DividendsResult = ResultEnvelope & {
  company: { ticker: string; cik: number; name: string };
  pays_dividends: boolean;
  basis: "declared" | "paid" | null;
  note: string | null;
  periods: DividendPeriod[];
};

type YearRow = { fiscalYear: number; quarters: (DividendPeriod | undefined)[]; year?: DividendPeriod };

/** Fiscal years newest first, each with its Q1..Q4 and full-year periods. */
function byFiscalYear(periods: DividendPeriod[]): YearRow[] {
  const rows = new Map<number, YearRow>();
  for (const p of periods) {
    const row = rows.get(p.fiscal_year) ?? { fiscalYear: p.fiscal_year, quarters: [undefined, undefined, undefined, undefined] };
    rows.set(p.fiscal_year, row);
    if (p.kind === "year") row.year = p;
    else {
      const n = /^Q([1-4]) /.exec(p.label);
      if (n) row.quarters[Number(n[1]) - 1] = p;
    }
  }
  return [...rows.values()].sort((a, b) => b.fiscalYear - a.fiscalYear);
}

// Shareable links: `/screener?tab=dividends&dividends_ticker=JPM`.
const URL_CODEC = fieldsCodec({ dividends_ticker: "AAPL" });

const money = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

export function DividendHistory() {
  const t = getMessages();
  const m = t.screener.dividends;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [ticker, setTicker] = useState(initial.dividends_ticker);
  const [query, setQuery] = useState({ ticker: initial.dividends_ticker.trim() });
  const { result, fieldErrors, error, pending, run } = useCompute("/screener/dividends", query);
  const history = result as DividendsResult | null;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share({ dividends_ticker: ticker.trim().toUpperCase() });
    if (ticker.trim() === query.ticker) run();
    else setQuery({ ticker: ticker.trim() });
  }

  function cell(p: DividendPeriod | undefined) {
    if (!p) return <span className="text-black/30 dark:text-white/30">–</span>;
    return (
      <a
        href={p.filing.url}
        target="_blank"
        rel="noreferrer"
        data-period={p.label}
        title={m.cellTitle(p.label, p.filing.form, p.filing.filed)}
        className="underline decoration-dotted"
      >
        {money(p.value)}
        {p.derived ? "*" : ""}
      </a>
    );
  }

  const rows = history ? byFiscalYear(history.periods) : [];
  return (
    <section aria-labelledby="dividends-section" className="mt-6 space-y-4">
      <h2 id="dividends-section" className="text-xl font-semibold">
        {m.heading}
      </h2>
      <p className="text-sm text-black/70 dark:text-white/70">{m.intro}</p>
      <form onSubmit={onSubmit} noValidate className="flex flex-wrap items-start gap-4">
        <div className="w-full max-w-[12rem]">
          <TextField name="dividend-ticker" label={m.ticker.label} hint={m.ticker.hint} value={ticker} onChange={setTicker} error={fieldErrors.ticker} />
        </div>
        <button
          type="submit"
          className="mt-6 rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {m.submit}
        </button>
      </form>

      <div aria-busy={pending} className="min-w-0 space-y-3">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {history ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 data-testid="dividends-heading" className="text-base font-semibold">
                {m.companyHeading(history.company.name, history.company.ticker)}
              </h3>
              {history.pays_dividends && (
                <ExportCsvButton
                  label={m.tableLabel}
                  filename={csvFilename("screener", "dividends", history.company.ticker)}
                  demo={history.source.is_demo}
                  table={{
                    columns: [...m.csvColumns],
                    rows: history.periods.map((p) => [p.label, p.start, p.end, p.value, p.derived ? "yes" : "", p.filing.form, p.filing.filed]),
                  }}
                />
              )}
            </div>
            {!history.pays_dividends ? (
              <p data-testid="dividends-note" className="text-sm text-black/70 dark:text-white/70">
                {history.note}
              </p>
            ) : (
              <>
                {history.basis && <p className="text-xs text-black/60 dark:text-white/60">{m.basis[history.basis]}</p>}
                <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
                  <table aria-label={m.tableLabel} className="w-full min-w-[32rem] border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-black/10 text-left dark:border-white/10">
                        <th scope="col" className="px-2 py-2 font-medium">
                          {m.fiscalYear}
                        </th>
                        {m.quarters.map((q) => (
                          <th key={q} scope="col" className="px-2 py-2 text-right font-medium">
                            {q}
                          </th>
                        ))}
                        <th scope="col" className="px-2 py-2 text-right font-medium">
                          {m.year}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.fiscalYear} data-fiscal-year={row.fiscalYear} className="border-b border-black/5 last:border-0 dark:border-white/5">
                          <th scope="row" className="px-2 py-1.5 text-left font-mono text-xs font-normal">
                            FY{row.fiscalYear}
                          </th>
                          {row.quarters.map((q, i) => (
                            <td key={i} className="px-2 py-1.5 text-right font-mono text-xs">
                              {cell(q)}
                            </td>
                          ))}
                          <td className="px-2 py-1.5 text-right font-mono text-xs font-semibold">{cell(row.year)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {history.periods.some((p) => p.derived) && <p className="text-xs text-black/60 dark:text-white/60">{m.derivedNote}</p>}
              </>
            )}
            <CalculationInfo result={history} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{m.loading}</p>
        )}
      </div>
    </section>
  );
}
