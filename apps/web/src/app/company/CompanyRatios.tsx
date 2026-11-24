"use client";

import { useState, type FormEvent } from "react";
import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricExplainer } from "@/components/MetricExplainer";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { csvFilename, type CsvTable } from "@/lib/csv";
import { decodeRows, encodeRows, useUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { useFrequency } from "./FrequencyToggle";
import { RatioInputs, type Selection } from "./RatioInputs";
import { formatRatio } from "./ratioFormat";

// Mirrors RatiosEnvelope in apps/compute/sextant_compute/company/ratios.py.
// Metrics are "<ratio id>:<TICKER>:<period id>"; the period id is the period end
// (fiscal year, or fiscal quarter with ?frequency=quarterly).
type Period = {
  id: string;
  label: string;
  fiscal_year: number;
  fiscal_quarter: number | null;
  end: string;
  filed: string;
  url: string;
};
type CompanyOut = { ticker: string; cik: number; name: string; price: number | null; periods: Period[] };
// basis: "ttm" (quarterly, trailing twelve months), "quarter_end" or "fiscal_year".
type RatioOut = { id: string; category: string; unit: string; basis: "fiscal_year" | "ttm" | "quarter_end" };
// `models` holds the scores (Altman Z, Piotroski F, Beneish M), the nine Piotroski
// signals and the DuPont burdens; the DuPont tables also reuse ratios from `ratios`.
type RatiosResult = ResultEnvelope & { companies: CompanyOut[]; ratios: RatioOut[]; models: RatioOut[] };

type Row = { ticker: string; price: string };
const CATEGORIES = ["efficiency", "liquidity", "profitability", "solvency", "valuation"] as const;
const DUPONT = {
  dupont3: ["return_on_equity", "net_margin", "asset_turnover", "equity_multiplier"],
  dupont5: [
    "return_on_equity",
    "dupont_tax_burden",
    "dupont_interest_burden",
    "operating_margin",
    "asset_turnover",
    "equity_multiplier",
  ],
} as const;
const GOOD_ZONES = new Set(["safe", "strong", "unlikely"]);
const BAD_ZONES = new Set(["distress", "weak", "likely"]);
const MAX_COMPANIES = 5;
const DEFAULT_ROWS: Row[] = [{ ticker: "AAPL", price: "" }];

/** A column: fiscal years, or fiscal quarters, aligned across companies by the company's own fiscal numbering. */
type Column = { key: number; label: string };
const columnKey = (p: Period) => p.fiscal_year * 4 + (p.fiscal_quarter ?? 0);
const columnLabel = (p: Period) => (p.fiscal_quarter ? p.label : `FY${p.fiscal_year}`);

// Shareable links: `/company?companies=MSFT:400,AAPL` (ticker:price). The
// statements form below owns `ticker`, so a link without `companies` shows the
// default company here (the screener links with both).
const URL_CODEC: UrlCodec<Row[]> = {
  keys: ["companies"],
  read(params) {
    const companies = params.get("companies");
    const rows = companies === null ? [] : decodeRows(companies, 2);
    return rows.length ? rows.map(([ticker, price]) => ({ ticker: ticker.toUpperCase(), price })) : DEFAULT_ROWS;
  },
  write: (rows) => ({ companies: encodeRows(rows.map((r) => [r.ticker.toUpperCase(), r.price])) }),
};

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

// DuPont tables repeat ratios shown elsewhere, so they tag values with
// data-dupont-value instead, keeping data-metric-value unique on the page.
type ValueAttr = "data-metric-value" | "data-dupont-value";

function Value(props: { id: string; result: MetricResult | undefined; attr: ValueAttr; drill?: string; onDrill?: () => void }) {
  const { drill, onDrill } = props;
  const value = <ValueText {...props} />;
  if (!props.result || !drill || !onDrill) return value;
  // Selecting a value opens its drill-down (formula and inputs).
  return (
    <button
      type="button"
      aria-label={drill}
      title={props.result.status === "ok" ? drill : undefined}
      onClick={onDrill}
      className="rounded-card text-right hover:bg-paper-2 focus-visible:outline focus-visible:outline-2"
    >
      {value}
    </button>
  );
}

function ValueText({ id, result, attr }: { id: string; result: MetricResult | undefined; attr: ValueAttr }) {
  const r = getMessages().companyRatios;
  if (!result) return <span className="text-muted">…</span>;
  const tag = { [attr]: id };
  if (result.status !== "ok" || result.value === null) {
    return (
      <span
        {...tag}
        data-status={result.status}
        title={result.reason ?? undefined}
        className="cursor-help text-xs italic text-muted underline decoration-dotted"
      >
        {r.missing}
        <span className="sr-only">: {result.reason}</span>
      </span>
    );
  }
  const zone = result.details.zone;
  return (
    <span {...tag} data-status="ok" className="tabular-nums">
      {formatRatio(result.value, result.unit, id)}
      {typeof zone === "string" && (
        <span
          data-zone={zone}
          className={`block text-xs ${
            GOOD_ZONES.has(zone)
              ? "text-success"
              : BAD_ZONES.has(zone)
                ? "text-red-700"
                : "text-warning"
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
  columns,
  note,
  attr = "data-metric-value",
  onDrill,
}: {
  category: string;
  ratios: RatioOut[];
  result: RatiosResult;
  columns: Column[];
  note?: string;
  attr?: ValueAttr;
  onDrill?: (selection: Omit<Selection, "frequency">) => void;
}) {
  const r = getMessages().companyRatios;
  const headingId = `ratios-${category}`;
  const many = result.companies.length > 1;
  const csv: CsvTable = {
    columns: [r.ratio, ...(many ? [r.companyColumn] : []), ...columns.map((col) => col.label)],
    rows: ratios.flatMap((ratio) =>
      result.companies.map((company) => {
        const byColumn = new Map(company.periods.map((p) => [columnKey(p), p]));
        return [
          r.ratios[ratio.id].name,
          ...(many ? [company.ticker] : []),
          ...columns.map((col) => {
            const period = byColumn.get(col.key);
            return period ? result.metrics[`${ratio.id}:${company.ticker}:${period.id}`] : null;
          }),
        ];
      }),
    ),
  };
  return (
    <section aria-labelledby={headingId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="text-lg">
          {r.categories[category]}
        </h3>
        <ExportCsvButton
          table={csv}
          label={r.categories[category]}
          filename={csvFilename("company-ratios", r.categories[category], result.companies.map((c) => c.ticker).join("_"))}
          demo={result.source.is_demo}
        />
      </div>
      {category === "valuation" && result.companies.some((c) => c.price === null) && (
        <p className="mt-1 text-xs text-muted">{r.priceNote}</p>
      )}
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
      <div className="relative mt-2 overflow-x-auto rounded-card border border-rule">
        <table aria-labelledby={headingId} className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-rule">
              <th scope="col" className="px-3 py-2 text-left font-medium">
                {r.ratio}
              </th>
              {many && (
                <th scope="col" className="px-3 py-2 text-left font-medium">
                  {r.companyColumn}
                </th>
              )}
              {columns.map((col) => (
                <th key={col.key} scope="col" className="px-3 py-2 text-right font-medium">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ratios.flatMap((ratio) =>
              result.companies.map((company, i) => {
                const byColumn = new Map(company.periods.map((p) => [columnKey(p), p]));
                return (
                  <tr
                    key={`${ratio.id}:${company.ticker}`}
                    className={`align-top ${i === result.companies.length - 1 ? "border-b border-rule last:border-0" : ""}`}
                  >
                    {i === 0 && (
                      <th
                        scope="row"
                        rowSpan={result.companies.length}
                        className="w-56 px-3 py-1.5 text-left font-normal"
                      >
                        {r.ratios[ratio.id].name}
                        {ratio.basis === "ttm" && (
                          <abbr
                            title={r.ttmTitle}
                            className="ml-1.5 rounded-card border border-muted px-1 text-[10px] font-medium no-underline"
                          >
                            {r.ttm}
                          </abbr>
                        )}
                        <MetricExplainer explainer={r.ratios[ratio.id]} />
                      </th>
                    )}
                    {many && <td className="px-3 py-1.5 tabular-nums text-xs">{company.ticker}</td>}
                    {columns.map((col) => {
                      const period = byColumn.get(col.key);
                      const id = period ? `${ratio.id}:${company.ticker}:${period.id}` : null;
                      return (
                        <td key={col.key} className="px-3 py-1.5 text-right">
                          {period && id ? (
                            <Value
                              id={id}
                              result={result.metrics[id]}
                              attr={attr}
                              drill={r.drill.open(r.ratios[ratio.id].name, `${period.label}${many ? ` (${company.ticker})` : ""}`)}
                              onDrill={
                                onDrill &&
                                (() =>
                                  onDrill({
                                    ratio: ratio.id,
                                    ticker: company.ticker,
                                    period: period.id,
                                    periodLabel: period.label,
                                    price: company.price,
                                  }))
                              }
                            />
                          ) : null}
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
  const { initial: initialRows, share } = useUrlInputs(URL_CODEC);
  const [rows, setRows] = useState<Row[]>(initialRows);
  const frequency = useFrequency();
  // Only submitted inputs are fetched: typing doesn't fire EDGAR requests.
  const [query, setQuery] = useState(() => toRequest(initialRows));
  const { result, fieldErrors, error, pending, run } = useCompute("/company/ratios", { ...query, frequency });
  const ratios = result as RatiosResult | null;
  const [selection, setSelection] = useState<Selection | null>(null);
  const drill = (s: Omit<Selection, "frequency">) => setSelection({ ...s, frequency });

  function setRow(i: number, field: keyof Row, value: string) {
    setRows((rs) => rs.map((row, j) => (j === i ? { ...row, [field]: value } : row)));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share(rows);
    const next = toRequest(rows);
    if (JSON.stringify(next) === JSON.stringify(query)) run();
    else setQuery(next);
  }

  const columns: Column[] = ratios
    ? [
        ...new Map(
          ratios.companies.flatMap((c) => c.periods.map((p) => [columnKey(p), { key: columnKey(p), label: columnLabel(p) }])),
        ).values(),
      ].sort((a, b) => a.key - b.key)
    : [];
  const quarterly = ratios?.companies.some((c) => c.periods.some((p) => p.fiscal_quarter)) ?? false;
  const inputClass = (err: string | undefined) =>
    `w-full min-w-0 rounded-card border px-3 py-2 tabular-nums ${
      err ? "border-error" : "border-muted"
    }`;

  return (
    <section data-testid="ratios" aria-labelledby="ratios-heading" className="mt-8 space-y-6">
      <div>
        <h2 id="ratios-heading" className="text-2xl">
          {r.heading}
        </h2>
        <p className="mt-1 text-sm text-ink-2">{r.intro}</p>
      </div>
      <form onSubmit={onSubmit} noValidate className="max-w-xl space-y-3">
        <fieldset className="min-w-0" aria-describedby={fieldErrors.companies ? fieldErrorId("companies") : undefined}>
          <legend className="text-sm font-medium">{r.inputsHeading}</legend>
          <p className="mt-1 text-xs text-muted">{r.inputsHint}</p>
          <div aria-hidden className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] gap-2 text-xs text-muted">
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
                      className="rounded-card px-2 py-1 text-lg leading-none text-muted hover:bg-paper-2 disabled:opacity-30"
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
            className="btn"
          >
            {r.add}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
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
            <p className="text-sm text-muted">
              {ratios.companies.map((c) => `${c.name} (${c.ticker})`).join(" · ")}
            </p>
            <p className="text-xs text-muted">{r.averageNote}</p>
            {quarterly && <p className="text-xs text-muted">{r.quarterlyNote}</p>}
            <RatioTable
              category="scores"
              ratios={ratios.models.filter((x) => x.category === "scores")}
              result={ratios}
              columns={columns}
              onDrill={drill}
              note={r.scoresNote}
            />
            <RatioTable
              category="piotroski"
              ratios={ratios.models.filter((x) => x.category === "piotroski")}
              result={ratios}
              columns={columns}
              onDrill={drill}
              note={r.piotroskiNote}
            />
            {CATEGORIES.map((category) => (
              <RatioTable
                key={category}
                category={category}
                ratios={ratios.ratios.filter((x) => x.category === category)}
                result={ratios}
                columns={columns}
                onDrill={drill}
              />
            ))}
            {(["dupont3", "dupont5"] as const).map((category) => {
              const byId = new Map([...ratios.ratios, ...ratios.models].map((x) => [x.id, x]));
              return (
                <RatioTable
                  key={category}
                  category={category}
                  ratios={DUPONT[category].flatMap((id) => byId.get(id) ?? [])}
                  result={ratios}
                  columns={columns}
                  note={r.dupontNotes[category]}
                  attr="data-dupont-value"
                />
              );
            })}
            <CalculationInfo result={ratios} />
            <AiExplain tool="company-ratios" result={ratios} />
          </>
        ) : (
          !error && <p className="text-sm text-muted">{r.loading}</p>
        )}
      </div>
      {selection && (
        <RatioInputs
          key={JSON.stringify(selection)}
          selection={selection}
          onClose={() => setSelection(null)}
        />
      )}
    </section>
  );
}
