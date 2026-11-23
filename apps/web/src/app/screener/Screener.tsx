"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricExplainer } from "@/components/MetricExplainer";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { DataSource, ResultEnvelope } from "@/lib/envelope";
import { PROVIDER_NAMES, useMyDataProviders } from "@/lib/myData";
import { decodeRows, encodeRows, useUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";

// Mirrors ScreenEnvelope in apps/compute/sextant_compute/screener/api.py.
type MetricId =
  | "revenue"
  | "revenue_growth"
  | "gross_margin"
  | "operating_margin"
  | "net_margin"
  | "roe"
  | "debt_ratio"
  | "current_ratio"
  | "change_52w"
  | "from_52w_high";
type Op = "min" | "max";
type SortColumn = "ticker" | "name" | MetricId;
type Direction = "asc" | "desc";
type Criterion = { metric: MetricId; op: Op; value: number | null };
type Column = { id: MetricId; label: string; unit: string };
type Row = { ticker: string; cik: number; name: string; period_end: string | null; values: Record<string, number | null> };
type Exclusion = { metric: string; label: string; count: number; reasons: { reason: string; count: number }[] };
type ScreenResult = ResultEnvelope & {
  year: number;
  default_year: number;
  frames: { flow: string; balance: string };
  criteria: Criterion[];
  columns: Column[];
  rows: Row[];
  universe: number;
  matched: number;
  excluded: { total: number; by_criterion: Exclusion[] };
  price_source: DataSource | null;
  prices_as_of: string | null;
};
type Query = { criteria: Criterion[]; year: number | null; sort: SortColumn; direction: Direction };

const METRICS: MetricId[] = [
  "revenue",
  "revenue_growth",
  "gross_margin",
  "operating_margin",
  "net_margin",
  "roe",
  "debt_ratio",
  "current_ratio",
];
// My data only: offered to users with a price data key, run on their own provider.
const PRICE_METRICS: MetricId[] = ["change_52w", "from_52w_high"];
const MAX_PRICED = 25; // MAX_PRICED in screener/api.py
// How each metric's value is entered: percent for decimals, USD millions for revenue.
const UNIT: Record<MetricId, "decimal" | "currency" | "ratio"> = {
  revenue: "currency",
  revenue_growth: "decimal",
  gross_margin: "decimal",
  operating_margin: "decimal",
  net_margin: "decimal",
  roe: "decimal",
  debt_ratio: "decimal",
  current_ratio: "ratio",
  change_52w: "decimal",
  from_52w_high: "decimal",
};
const SCALE = { decimal: 100, currency: 1e-6, ratio: 1 } as const;

type FormRow = { key: number; metric: MetricId; op: Op; value: string };
const DEFAULT_ROWS: FormRow[] = [
  { key: 1, metric: "revenue_growth", op: "min", value: "10" },
  { key: 2, metric: "gross_margin", op: "min", value: "40" },
  { key: 3, metric: "roe", op: "min", value: "15" },
];

function toCriterion(row: FormRow): Criterion {
  const raw = row.value.trim();
  const n = raw === "" ? null : Number(raw);
  // An unknown metric (from a hand-edited link) goes as is: the API names the field.
  const value = n === null || Number.isNaN(n) ? null : n / (SCALE[UNIT[row.metric]] ?? 1);
  return { metric: row.metric, op: row.op, value };
}

function columnsFor(criteria: Criterion[]): MetricId[] {
  return Array.from(new Set<MetricId>(["revenue", ...criteria.map((c) => c.metric)]));
}

const PCT = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const MILLIONS = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const TWO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function formatCell(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "–";
  if (unit === "decimal") return PCT.format(value);
  if (unit === "currency") return MILLIONS.format(value / 1e6);
  return TWO.format(value);
}

const DEFAULT_QUERY: Query = {
  criteria: DEFAULT_ROWS.map(toCriterion),
  year: null,
  sort: "revenue",
  direction: "desc",
};

// Shareable links: `/screener?criteria=revenue_growth:min:10,roe:min:15&year=2024&sort=roe&direction=desc`.
// Criteria values are in the form's units (percent, USD millions).
type UrlForm = { rows: FormRow[]; year: string; sort: string; direction: string };
const URL_CODEC: UrlCodec<UrlForm> = {
  keys: ["criteria", "year", "sort", "direction"],
  read(params) {
    const raw = params.get("criteria");
    const rows =
      raw === null
        ? DEFAULT_ROWS
        : decodeRows(raw, 3).map(([metric, op, value], i) => ({ key: i + 1, metric: metric as MetricId, op: op as Op, value }));
    return {
      rows,
      year: params.get("year") ?? "",
      sort: params.get("sort") ?? DEFAULT_QUERY.sort,
      direction: params.get("direction") ?? DEFAULT_QUERY.direction,
    };
  },
  write: ({ rows, year, sort, direction }) => ({
    criteria: encodeRows(rows.map((r) => [r.metric, r.op, r.value])),
    year: year || null,
    sort,
    direction,
  }),
};

/** The screen a link asks for. Bad values go as typed so the API reports them. */
function toQuery({ rows, year, sort, direction }: UrlForm): Query {
  const n = Number(year);
  return {
    criteria: rows.map(toCriterion),
    year: year === "" ? null : Number.isInteger(n) ? n : (year as unknown as number),
    sort: sort as SortColumn,
    direction: direction as Direction,
  };
}

/** The default (latest complete) year and the seven before it. */
function yearOptions(latest: number | undefined): number[] {
  return latest ? Array.from({ length: 8 }, (_, i) => latest - i) : [];
}

function SortHeader({
  column,
  label,
  align = "right",
  sort,
  direction,
  onSort,
}: {
  column: SortColumn;
  label: string;
  align?: "left" | "right";
  sort: SortColumn;
  direction: Direction;
  onSort: (column: SortColumn) => void;
}) {
  const active = sort === column;
  return (
    <th
      scope="col"
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : undefined}
      className={`px-2 py-2 font-medium ${align === "left" ? "text-left" : "text-right"}`}
    >
      <button type="button" onClick={() => onSort(column)} className="inline-flex items-center gap-1 hover:underline">
        {label}
        <span aria-hidden="true" className="text-xs text-black/40 dark:text-white/40">
          {active ? (direction === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

const inputClass =
  "mt-1 w-full min-w-0 rounded-md border border-black/20 px-2 py-2 dark:border-white/20 dark:bg-white/5";

export function Screener() {
  const t = getMessages();
  const s = t.screener;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [rows, setRows] = useState<FormRow[]>(initial.rows);
  const [nextKey, setNextKey] = useState(initial.rows.length + 1);
  const [year, setYear] = useState(initial.year);
  // Only a submitted screen is fetched: editing criteria doesn't hit EDGAR.
  const [query, setQuery] = useState<Query>(() => toQuery(initial));
  // The form as last submitted: sorting re-shares it, not unsubmitted edits.
  const [submitted, setSubmitted] = useState({ rows: initial.rows, year: initial.year });
  // Price criteria run on the user's own provider; a link with them opened
  // without a key gets the API's "needs My data" message on the criterion.
  const providers = useMyDataProviders();
  const priceSource = providers[0] ?? null;
  const hasPriceCriteria = query.criteria.some((c) => PRICE_METRICS.includes(c.metric));
  const body = hasPriceCriteria && priceSource ? { ...query, price_source: priceSource } : query;
  const { result, fieldErrors, error, pending, run } = useCompute("/screener/screen", body);
  const screen = result as ScreenResult | null;

  function update(key: number, patch: Partial<FormRow>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const criteria = rows.map(toCriterion);
    const cols = columnsFor(criteria);
    const sort = query.sort === "ticker" || query.sort === "name" || cols.includes(query.sort) ? query.sort : "revenue";
    const next: Query = {
      criteria,
      year: year ? Number(year) : null,
      sort,
      direction: sort === query.sort ? query.direction : "desc",
    };
    setSubmitted({ rows, year });
    share({ rows, year, sort: next.sort, direction: next.direction });
    if (JSON.stringify(next) === JSON.stringify(query)) run();
    else setQuery(next);
  }

  function sortBy(column: SortColumn) {
    const next: Query =
      query.sort === column
        ? { ...query, direction: query.direction === "asc" ? "desc" : "asc" }
        : { ...query, sort: column, direction: column === "ticker" || column === "name" ? "asc" : "desc" };
    share({ ...submitted, sort: next.sort, direction: next.direction });
    setQuery(next);
  }

  const sortProps = { sort: query.sort, direction: query.direction, onSort: sortBy };

  return (
    <section aria-labelledby="screen-heading" className="mt-8 space-y-6">
      <h2 id="screen-heading" className="text-xl font-semibold">
        {s.screenHeading}
      </h2>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">{s.criteriaLegend}</legend>
          {rows.map((row, i) => {
            const n = i + 1;
            const valueName = `criteria.${i}.value`;
            const valueError = fieldErrors[valueName] ?? fieldErrors[`criteria.${i}.metric`];
            return (
              <div key={row.key} className="flex flex-wrap items-end gap-2">
                <div className="min-w-0 flex-1 basis-40">
                  <label htmlFor={`criterion-metric-${row.key}`} className="sr-only">
                    {s.metricLabel} {n}
                  </label>
                  <select
                    id={`criterion-metric-${row.key}`}
                    value={row.metric}
                    onChange={(e) => update(row.key, { metric: e.target.value as MetricId })}
                    className={inputClass}
                  >
                    {[...METRICS, ...(priceSource || PRICE_METRICS.includes(row.metric) ? PRICE_METRICS : [])].map((m) => (
                      <option key={m} value={m}>
                        {s.metrics[m]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="w-28">
                  <label htmlFor={`criterion-op-${row.key}`} className="sr-only">
                    {s.opLabel} {n}
                  </label>
                  <select
                    id={`criterion-op-${row.key}`}
                    value={row.op}
                    onChange={(e) => update(row.key, { op: e.target.value as Op })}
                    className={inputClass}
                  >
                    <option value="min">{s.ops.min}</option>
                    <option value="max">{s.ops.max}</option>
                  </select>
                </div>
                <div className="w-36">
                  <label htmlFor={`criterion-value-${row.key}`} className="sr-only">
                    {s.valueLabel} {n}
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      id={`criterion-value-${row.key}`}
                      name={valueName}
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={row.value}
                      onChange={(e) => update(row.key, { value: e.target.value })}
                      aria-invalid={valueError ? true : undefined}
                      aria-describedby={valueError ? fieldErrorId(valueName) : undefined}
                      className={`${inputClass} font-mono ${valueError ? "border-red-500" : ""}`}
                    />
                    <span className="mt-1 text-sm text-black/60 dark:text-white/60">{s.valueUnits[UNIT[row.metric]]}</span>
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={`${s.removeLabel} ${n}`}
                  onClick={() => setRows((rs) => rs.filter((r) => r.key !== row.key))}
                  className="mb-0.5 rounded-md border border-black/20 px-3 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                >
                  {s.remove}
                </button>
                <div className="basis-full">
                  <FieldError name={valueName} message={valueError} />
                </div>
              </div>
            );
          })}
          <FieldError name="criteria" message={fieldErrors.criteria} />
        </fieldset>
        <div className="flex flex-wrap items-end gap-4">
          <button
            type="button"
            onClick={() => {
              setRows((rs) => [...rs, { key: nextKey, metric: "net_margin", op: "min", value: "10" }]);
              setNextKey((k) => k + 1);
            }}
            className="rounded-md border border-black/20 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          >
            {s.add}
          </button>
          <div className="w-48">
            <label htmlFor="input-year" className="block text-sm font-medium">
              {s.year.label}
            </label>
            <select id="input-year" value={year} onChange={(e) => setYear(e.target.value)} className={inputClass}>
              <option value="">{screen ? s.year.latestIs(screen.default_year) : s.year.latest}</option>
              {yearOptions(screen?.default_year).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
            <FieldError name="year" message={fieldErrors.year} />
          </div>
          <button
            type="submit"
            className="rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
          >
            {s.run}
          </button>
        </div>
        <p data-testid="price-criteria-note" className="text-xs text-black/50 dark:text-white/50">
          {priceSource ? s.priceCriteria.myData(PROVIDER_NAMES[priceSource], MAX_PRICED) : s.priceCriteria.signIn}
        </p>
      </form>

      <div data-testid="results" aria-busy={pending} className="min-w-0 space-y-4">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {screen ? (
          <>
            <div data-testid="screen-summary" className="space-y-1 text-sm">
              <p className="font-medium">
                {s.match(screen.matched, screen.universe)}
                {screen.rows.length < screen.matched ? s.showing(screen.rows.length) : ""} · {screen.frames.flow}.{" "}
                {screen.excluded.total ? `${s.excluded(screen.excluded.total)}:` : s.noneExcluded}
              </p>
              {screen.excluded.total > 0 && (
                <ul className="list-disc pl-5 text-black/70 dark:text-white/70">
                  {screen.excluded.by_criterion
                    .filter((e) => e.count > 0)
                    .map((e) => (
                      <li key={e.metric}>
                        <span>
                          {e.label}: {e.count}
                        </span>{" "}
                        — {e.reasons.map((r) => `${r.reason} (${r.count})`).join("; ")}
                      </li>
                    ))}
                </ul>
              )}
              {screen.price_source && (
                <p data-testid="prices-info" className="text-black/70 dark:text-white/70">
                  {s.pricesInfo(screen.price_source.name, screen.prices_as_of ?? "–")}
                </p>
              )}
              <MetricExplainer explainer={s.explainer} />
              {screen.price_source && <MetricExplainer explainer={s.priceExplainer} />}
            </div>
            {screen.rows.length === 0 ? (
              <p className="text-sm text-black/60 dark:text-white/60">{s.noMatches}</p>
            ) : (
              <div className="flex justify-end">
                <ExportCsvButton
                  label={s.resultsLabel}
                  filename={csvFilename("screener", "results", String(screen.year))}
                  demo={screen.source.is_demo}
                  table={{
                    columns: [s.ticker, s.company, ...screen.columns.map((c) => c.label), s.fiscalYearEnd],
                    rows: screen.rows.map((r) => [
                      r.ticker,
                      r.name,
                      ...screen.columns.map((c) => r.values[c.id]),
                      r.period_end,
                    ]),
                  }}
                />
              </div>
            )}
            {screen.rows.length > 0 && (
              <div className="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
                <table aria-label={s.resultsLabel} className="w-full min-w-[40rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-black/10 align-bottom dark:border-white/10">
                      <SortHeader column="ticker" label={s.ticker} align="left" {...sortProps} />
                      <SortHeader column="name" label={s.company} align="left" {...sortProps} />
                      {screen.columns.map((c) => (
                        <SortHeader key={c.id} column={c.id} label={c.label} {...sortProps} />
                      ))}
                      <th scope="col" className="px-2 py-2 text-right font-medium">
                        {s.fiscalYearEnd}
                      </th>
                      <th scope="col" className="px-2 py-2 text-left font-medium">
                        {s.open}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {screen.rows.map((r) => (
                      <tr key={r.cik} data-ticker={r.ticker} className="border-b border-black/5 last:border-0 dark:border-white/5">
                        <td className="px-2 py-1.5 font-mono">{r.ticker}</td>
                        <td className="px-2 py-1.5">{r.name}</td>
                        {screen.columns.map((c) => (
                          <td key={c.id} data-metric-value={c.id} className="px-2 py-1.5 text-right font-mono tabular-nums">
                            {formatCell(r.values[c.id], c.unit)}
                          </td>
                        ))}
                        <td className="px-2 py-1.5 text-right font-mono text-xs">{r.period_end ?? "–"}</td>
                        <td className="whitespace-nowrap px-2 py-1.5">
                          <Link href={`/company?ticker=${encodeURIComponent(r.ticker)}`} className="underline">
                            {s.healthCheck}
                          </Link>{" "}
                          ·{" "}
                          <Link href={`/valuation?ticker=${encodeURIComponent(r.ticker)}`} className="underline">
                            {s.valuation}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="text-xs text-black/50 dark:text-white/50">{s.unitsNote}</p>
            <CalculationInfo result={screen} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{s.loading}</p>
        )}
      </div>
    </section>
  );
}
