"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { MetricExplainer } from "@/components/MetricExplainer";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { formatValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";

// Mirrors RatiosEnvelope in apps/compute/sextant_compute/company/ratios.py.
// Metrics are "<ratio id>:<TICKER>:<period id>"; the period id is the fiscal year end.
type Period = { id: string; label: string; fiscal_year: number; end: string; filed: string; url: string };
type CompanyOut = { ticker: string; cik: number; name: string; price: number | null; periods: Period[] };
type RatioOut = { id: string; category: string; unit: string };
type RatiosResult = ResultEnvelope & { companies: CompanyOut[]; ratios: RatioOut[] };

type Row = { ticker: string; price: string };
const CATEGORIES = ["efficiency", "liquidity", "profitability", "solvency", "valuation"] as const;
const ALTMAN: RatioOut = { id: "altman_z", category: "distress", unit: "score" };
const MAX_COMPANIES = 5;
const DEFAULT_ROWS: Row[] = [{ ticker: "AAPL", price: "" }];

const TWO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ONE = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function formatRatio(value: number, unit: string | null): string {
  const r = getMessages().companyRatios;
  if (unit === "days") return `${ONE.format(value)} ${r.days}`;
  if (unit === "currency") return `${WHOLE.format(value / 1e6)}${r.currencyMillions}`;
  if (unit === "per_share" || unit === "score" || unit === "ratio") return TWO.format(value);
  return formatValue(value, unit);
}

function toRequest(rows: Row[]) {
  return {
    companies: rows.map((r) => ({
      ticker: r.ticker.trim(),
      // Empty means "no price"; anything else goes as typed so the API can report it.
      price: r.price.trim() === "" ? null : Number.isFinite(Number(r.price)) ? Number(r.price) : r.price,
    })),
    years: 5,
  };
}

function Value({ id, result }: { id: string; result: MetricResult | undefined }) {
  const r = getMessages().companyRatios;
  if (!result) return <span className="text-black/40 dark:text-white/40">…</span>;
  if (result.status !== "ok" || result.value === null) {
    return (
      <span
        data-metric-value={id}
        data-status={result.status}
        title={result.reason ?? undefined}
        className="cursor-help text-xs italic text-black/50 underline decoration-dotted dark:text-white/50"
      >
        {r.missing}
        <span className="sr-only">: {result.reason}</span>
      </span>
    );
  }
  const zone = result.details.zone;
  return (
    <span data-metric-value={id} data-status="ok" className="font-mono tabular-nums">
      {formatRatio(result.value, result.unit)}
      {typeof zone === "string" && (
        <span
          data-zone={zone}
          className={`block font-sans text-xs ${
            zone === "safe"
              ? "text-green-700 dark:text-green-400"
              : zone === "distress"
                ? "text-red-700 dark:text-red-400"
                : "text-amber-700 dark:text-amber-400"
          }`}
        >
          {r.zones[zone]}
        </span>
      )}
    </span>
  );
}

function RatioTable({
  category,
  ratios,
  result,
  years,
}: {
  category: string;
  ratios: RatioOut[];
  result: RatiosResult;
  years: number[];
}) {
  const r = getMessages().companyRatios;
  const headingId = `ratios-${category}`;
  const many = result.companies.length > 1;
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} className="text-base font-semibold">
        {r.categories[category]}
      </h3>
      {category === "valuation" && result.companies.some((c) => c.price === null) && (
        <p className="mt-1 text-xs text-black/60 dark:text-white/60">{r.priceNote}</p>
      )}
      <div className="relative mt-2 overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
        <table aria-labelledby={headingId} className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-black/10 dark:border-white/10">
              <th scope="col" className="px-3 py-2 text-left font-medium">
                {r.ratio}
              </th>
              {many && (
                <th scope="col" className="px-3 py-2 text-left font-medium">
                  {r.companyColumn}
                </th>
              )}
              {years.map((fy) => (
                <th key={fy} scope="col" className="px-3 py-2 text-right font-medium">
                  FY{fy}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ratios.flatMap((ratio) =>
              result.companies.map((company, i) => {
                const byYear = new Map(company.periods.map((p) => [p.fiscal_year, p]));
                return (
                  <tr
                    key={`${ratio.id}:${company.ticker}`}
                    className={`align-top ${i === result.companies.length - 1 ? "border-b border-black/5 last:border-0 dark:border-white/5" : ""}`}
                  >
                    {i === 0 && (
                      <th
                        scope="row"
                        rowSpan={result.companies.length}
                        className="w-56 px-3 py-1.5 text-left font-normal"
                      >
                        {r.ratios[ratio.id].name}
                        <MetricExplainer explainer={r.ratios[ratio.id]} />
                      </th>
                    )}
                    {many && <td className="px-3 py-1.5 font-mono text-xs">{company.ticker}</td>}
                    {years.map((fy) => {
                      const period = byYear.get(fy);
                      const id = period ? `${ratio.id}:${company.ticker}:${period.id}` : null;
                      return (
                        <td key={fy} className="px-3 py-1.5 text-right">
                          {id ? <Value id={id} result={result.metrics[id]} /> : null}
                        </td>
                      );
                    })}
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function CompanyRatios() {
  const t = getMessages();
  const r = t.companyRatios;
  const [rows, setRows] = useState<Row[]>(DEFAULT_ROWS);
  // Only submitted inputs are fetched: typing doesn't fire EDGAR requests.
  const [query, setQuery] = useState(() => toRequest(DEFAULT_ROWS));
  const { result, fieldErrors, error, pending, run } = useCompute("/company/ratios", query);
  const ratios = result as RatiosResult | null;

  function setRow(i: number, field: keyof Row, value: string) {
    setRows((rs) => rs.map((row, j) => (j === i ? { ...row, [field]: value } : row)));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next = toRequest(rows);
    if (JSON.stringify(next) === JSON.stringify(query)) run();
    else setQuery(next);
  }

  const years = ratios
    ? [...new Set(ratios.companies.flatMap((c) => c.periods.map((p) => p.fiscal_year)))].sort((a, b) => a - b)
    : [];
  const inputClass = (err: string | undefined) =>
    `w-full min-w-0 rounded-md border px-3 py-2 font-mono dark:bg-white/5 ${
      err ? "border-red-500" : "border-black/20 dark:border-white/20"
    }`;

  return (
    <section data-testid="ratios" aria-labelledby="ratios-heading" className="mt-8 space-y-6">
      <div>
        <h2 id="ratios-heading" className="text-xl font-semibold">
          {r.heading}
        </h2>
        <p className="mt-1 text-sm text-black/70 dark:text-white/70">{r.intro}</p>
      </div>
      <form onSubmit={onSubmit} noValidate className="max-w-xl space-y-3">
        <fieldset className="min-w-0" aria-describedby={fieldErrors.companies ? fieldErrorId("companies") : undefined}>
          <legend className="text-sm font-medium">{r.inputsHeading}</legend>
          <p className="mt-1 text-xs text-black/50 dark:text-white/50">{r.inputsHint}</p>
          <div aria-hidden className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] gap-2 text-xs text-black/60 dark:text-white/60">
            <span>{r.companyColumn}</span>
            <span>
              {r.price} {r.priceUnit}
            </span>
          </div>
          <ol className="mt-1 space-y-2">
            {rows.map((row, i) => {
              const n = i + 1;
              const tickerName = `companies.${i}.ticker`;
              const priceName = `companies.${i}.price`;
              return (
                <li key={i} className="min-w-0">
                  <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-2">
                    <input
                      name={tickerName}
                      aria-label={`${r.company} ${n}`}
                      autoCapitalize="characters"
                      spellCheck={false}
                      value={row.ticker}
                      onChange={(e) => setRow(i, "ticker", e.target.value)}
                      aria-invalid={fieldErrors[tickerName] ? true : undefined}
                      aria-describedby={fieldErrors[tickerName] ? fieldErrorId(tickerName) : undefined}
                      className={inputClass(fieldErrors[tickerName])}
                    />
                    <input
                      name={priceName}
                      aria-label={`${r.price} ${n}`}
                      inputMode="decimal"
                      value={row.price}
                      onChange={(e) => setRow(i, "price", e.target.value)}
                      aria-invalid={fieldErrors[priceName] ? true : undefined}
                      aria-describedby={fieldErrors[priceName] ? fieldErrorId(priceName) : undefined}
                      className={inputClass(fieldErrors[priceName])}
                    />
                    <button
                      type="button"
                      aria-label={`${r.remove} ${n}`}
                      disabled={rows.length === 1}
                      onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                      className="rounded-md px-2 py-1 text-lg leading-none text-black/60 hover:bg-black/5 disabled:opacity-30 dark:text-white/60 dark:hover:bg-white/10"
                    >
                      ×
                    </button>
                  </div>
                  <FieldError name={tickerName} message={fieldErrors[tickerName]} />
                  <FieldError name={priceName} message={fieldErrors[priceName]} />
                </li>
              );
            })}
          </ol>
          <FieldError name="companies" message={fieldErrors.companies} />
        </fieldset>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={rows.length >= MAX_COMPANIES}
            onClick={() => setRows((rs) => [...rs, { ticker: "", price: "" }])}
            className="rounded-md border border-black/20 px-3 py-2 text-sm hover:bg-black/5 disabled:opacity-40 dark:border-white/20 dark:hover:bg-white/10"
          >
            {r.add}
          </button>
          <button
            type="submit"
            className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {r.submit}
          </button>
        </div>
      </form>

      <div data-testid="ratio-results" aria-busy={pending} className="min-w-0 space-y-6">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {ratios ? (
          <>
            <p className="text-sm text-black/60 dark:text-white/60">
              {ratios.companies.map((c) => `${c.name} (${c.ticker})`).join(" · ")}
            </p>
            <p className="text-xs text-black/50 dark:text-white/50">{r.averageNote}</p>
            <RatioTable category="distress" ratios={[ALTMAN]} result={ratios} years={years} />
            {CATEGORIES.map((category) => (
              <RatioTable
                key={category}
                category={category}
                ratios={ratios.ratios.filter((x) => x.category === category)}
                result={ratios}
                years={years}
              />
            ))}
            <CalculationInfo result={ratios} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{r.loading}</p>
        )}
      </div>
    </section>
  );
}
