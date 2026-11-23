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

// Mirrors FilingsEnvelope in apps/compute/sextant_compute/screener/api.py.
type Filing = { form: string; title: string; company: string; cik: number; filed: string; accession: string; url: string };
type FilingsResult = ResultEnvelope & { scope: "market" | "company"; company: string | null; filings: Filing[] };
type Query = { ticker: string; form: string };

// Must match FilingForm in the compute request model.
const FORMS = ["10-K", "10-Q", "8-K", "4", "S-1", "DEF 14A", "20-F", "6-K"];
// Shareable links: `/screener?filings_ticker=MSFT&filings_form=10-K` (blank ticker = market-wide).
// Prefixed so they don't collide with the screen's params on the same page.
const URL_CODEC = fieldsCodec({ filings_ticker: "", filings_form: "" });

export function LatestFilings() {
  const t = getMessages();
  const f = t.screener.filings;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [scope, setScope] = useState<"market" | "company">(initial.filings_ticker ? "company" : "market");
  const [ticker, setTicker] = useState(initial.filings_ticker);
  const [form, setForm] = useState(initial.filings_form);
  const [query, setQuery] = useState<Query>({ ticker: initial.filings_ticker.trim(), form: initial.filings_form });
  const { result, fieldErrors, error, pending, run } = useCompute("/screener/filings", query);
  const list = result as FilingsResult | null;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next = { ticker: scope === "company" ? ticker.trim() : "", form };
    share({ filings_ticker: next.ticker.toUpperCase(), filings_form: form });
    if (next.ticker === query.ticker && next.form === query.form) run();
    else setQuery(next);
  }

  return (
    <section aria-labelledby="filings-section" className="mt-12 space-y-4">
      <h2 id="filings-section" className="text-xl font-semibold">
        {f.heading}
      </h2>
      <form onSubmit={onSubmit} noValidate className="flex flex-wrap items-end gap-4">
        <fieldset className="flex flex-wrap gap-4">
          <legend className="sr-only">{f.scopeLegend}</legend>
          {(["market", "company"] as const).map((value) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="filings-scope"
                value={value}
                checked={scope === value}
                onChange={() => setScope(value)}
              />
              {value === "market" ? f.market : f.company}
            </label>
          ))}
        </fieldset>
        {scope === "company" && (
          <div className="w-full max-w-[12rem]">
            <TextField
              name="ticker"
              label={f.ticker.label}
              hint={f.ticker.hint}
              value={ticker}
              onChange={setTicker}
              error={fieldErrors.ticker}
            />
          </div>
        )}
        <div className="w-40">
          <label htmlFor="input-form" className="block text-sm font-medium">
            {f.form}
          </label>
          <select
            id="input-form"
            value={form}
            onChange={(e) => setForm(e.target.value)}
            className="mt-1 w-full rounded-md border border-black/20 px-2 py-2 dark:border-white/20 dark:bg-white/5"
          >
            <option value="">{f.allForms}</option>
            {FORMS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {f.submit}
        </button>
      </form>

      <div aria-busy={pending} className="min-w-0 space-y-3">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {list ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 data-testid="filings-heading" className="text-base font-semibold">
                {list.scope === "company" && list.company ? f.companyHeading(list.company) : f.marketHeading}
              </h3>
              {list.filings.length > 0 && (
                <ExportCsvButton
                  label={f.tableLabel}
                  filename={csvFilename(
                    "screener",
                    "filings",
                    [query.ticker || "market", query.form].filter(Boolean).join("_"),
                  )}
                  demo={list.source.is_demo}
                  table={{
                    columns: [f.formColumn, f.title, f.companyColumn, f.filed],
                    rows: list.filings.map((row) => [row.form, row.title, row.company, row.filed]),
                  }}
                />
              )}
            </div>
            {list.filings.length === 0 ? (
              <p className="text-sm text-black/60 dark:text-white/60">{f.none}</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
                <table aria-label={f.tableLabel} className="w-full min-w-[36rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-black/10 text-left dark:border-white/10">
                      <th scope="col" className="px-2 py-2 font-medium">
                        {f.formColumn}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {f.title}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {f.companyColumn}
                      </th>
                      <th scope="col" className="px-2 py-2 font-medium">
                        {f.filed}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.filings.map((row, i) => (
                      <tr key={`${row.accession}-${row.cik}-${i}`} className="border-b border-black/5 last:border-0 dark:border-white/5">
                        <td className="whitespace-nowrap px-2 py-1.5 font-mono text-xs">{row.form}</td>
                        <td className="px-2 py-1.5">
                          <a href={row.url} target="_blank" rel="noreferrer" className="underline decoration-dotted">
                            {row.title}
                          </a>
                        </td>
                        <td className="px-2 py-1.5">{row.company}</td>
                        <td className="whitespace-nowrap px-2 py-1.5 font-mono text-xs">{row.filed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <CalculationInfo result={list} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{f.loading}</p>
        )}
      </div>
    </section>
  );
}
