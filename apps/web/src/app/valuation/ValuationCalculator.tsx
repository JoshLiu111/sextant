"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { DataModeToggle } from "@/components/DataModeToggle";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { MetricCard, type MetricCardValue } from "@/components/MetricCard";
import { MetricExplainer, type Explainer } from "@/components/MetricExplainer";
import { NumberField } from "@/components/NumberField";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { csvFilename } from "@/lib/csv";
import { formatMoneyValue } from "@/lib/format";
import { DEMO_SOURCE, PROVIDER_NAMES, useMyDataProviders, type PriceSource } from "@/lib/myData";
import type { AssumptionSetBody, ValuationAssumptions } from "@/lib/valuationAssumptions";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { DEFAULT_TICKER } from "./defaults";
import { SavedAssumptions } from "./SavedAssumptions";

// Mirrors ValuationEnvelope in apps/compute/sextant_compute/valuation/api.py.
// Sensitivity cells are metrics "sensitivity:<growth index>:<discount index>".
type ValuationResult = ResultEnvelope & {
  company: { ticker: string; cik: number; name: string };
  base_period: { id: string; label: string; filed: string; url: string };
  sensitivity: { growth_rates: number[]; discount_rates: number[] };
  /** The My data provider the share price came from; null when typed in or absent. */
  price_source: { id: string; name: string; is_demo: boolean } | null;
};

// Form state uses display units (percent); the request model uses decimals.
const NUMBER_FIELDS = [
  "forecast_years",
  "growth_rate",
  "terminal_growth",
  "discount_rate",
  "risk_free_rate",
  "beta",
  "equity_risk_premium",
  "cost_of_equity",
  "cost_of_debt",
  "tax_rate",
  "debt_weight",
  "share_price",
] as const;
type NumberFieldId = (typeof NUMBER_FIELDS)[number];
type Form = Record<NumberFieldId, string>;

const DEFAULTS: Form = {
  forecast_years: "5",
  growth_rate: "5",
  terminal_growth: "2.5",
  discount_rate: "",
  risk_free_rate: "4.5",
  beta: "1",
  equity_risk_premium: "5",
  cost_of_equity: "",
  cost_of_debt: "",
  tax_rate: "",
  debt_weight: "",
  share_price: "",
};
// Shareable links: `/valuation?ticker=MSFT&growth_rate=8` (the screener links
// with just the ticker). Submitting writes the ticker and every assumption.
const URL_CODEC = fieldsCodec({ ticker: DEFAULT_TICKER, ...DEFAULTS });

const DCF_FIELDS: NumberFieldId[] = ["forecast_years", "growth_rate", "terminal_growth", "discount_rate"];
const WACC_FIELDS: NumberFieldId[] = [
  "risk_free_rate",
  "beta",
  "equity_risk_premium",
  "cost_of_equity",
  "cost_of_debt",
  "tax_rate",
  "debt_weight",
  "share_price",
];
const PERCENT_FIELDS = new Set<NumberFieldId>([
  "growth_rate",
  "terminal_growth",
  "discount_rate",
  "risk_free_rate",
  "equity_risk_premium",
  "cost_of_equity",
  "cost_of_debt",
  "tax_rate",
  "debt_weight",
]);
// Blank input is sent as null: for the override fields (discount rate, cost of
// equity/debt, tax rate, debt weight, share price) that means "derive it"; for
// the others the API reports the field as required.

function toNumber(raw: string, percent: boolean): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return percent ? n / 100 : n;
}

function toAssumptions(form: Form): AssumptionSetBody["assumptions"] {
  const out = {} as AssumptionSetBody["assumptions"];
  for (const field of NUMBER_FIELDS) out[field] = toNumber(form[field], PERCENT_FIELDS.has(field));
  return out;
}

/** A saved set back into form strings: percent fields in percent, without float noise (0.07 * 100). */
function fromAssumptions(saved: ValuationAssumptions): Form {
  const form = { ...DEFAULTS };
  for (const field of NUMBER_FIELDS) {
    const value = saved[field];
    const shown = PERCENT_FIELDS.has(field) && value !== null ? value * 100 : value;
    form[field] = shown === null ? "" : String(Number(shown.toPrecision(12)));
  }
  return form;
}

function toRequest(ticker: string, form: Form, priceSource: PriceSource) {
  return { ticker, price_source: priceSource, ...toAssumptions(form) };
}

const PERCENT_AXIS = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 2 });

function priceNote(result: ValuationResult): string | undefined {
  const price = result.metrics.share_price;
  if (price?.details.basis === "latest_close" && result.price_source)
    return getMessages().valuation.latestClose(result.price_source.name, String(price.details.date));
  return basisNote(price);
}

function basisNote(result: MetricResult | undefined): string | undefined {
  const basis = result?.details.basis;
  return typeof basis === "string" ? getMessages().valuation.basis[basis] : undefined;
}

function Card({ id, explainer, values }: { id: string; explainer: Explainer; values: MetricCardValue[] }) {
  return <MetricCard id={id} explainer={explainer} values={values} format={formatMoneyValue} />;
}

function SensitivityTable({ result }: { result: ValuationResult }) {
  const v = getMessages().valuation;
  const { growth_rates, discount_rates } = result.sensitivity;
  const center = Math.floor(growth_rates.length / 2);
  const columns = discount_rates.length ? discount_rates : [null, null, null, null, null];
  return (
    <section data-testid="sensitivity" aria-labelledby="sensitivity-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="sensitivity-heading" className="text-lg font-semibold">
          {v.sections.sensitivity}
        </h2>
        <ExportCsvButton
          label={v.sections.sensitivity}
          filename={csvFilename("valuation", "sensitivity", result.company.ticker)}
          demo={result.source.is_demo}
          table={{
            // Rates as decimals (0.05 = 5%), like the request model.
            columns: [`${v.growthAxis} \\ ${v.discountAxis}`, ...discount_rates.map(String)],
            rows: growth_rates.map((g, i) => [g, ...discount_rates.map((_, j) => result.metrics[`sensitivity:${i}:${j}`])]),
          }}
        />
      </div>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60">{v.sensitivityCaption}</p>
      <div className="mt-2 overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
        <table aria-labelledby="sensitivity-heading" className="w-full min-w-[28rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-black/10 dark:border-white/10">
              <th scope="col" className="px-3 py-2 text-left font-medium">
                {v.growthAxis} \ {v.discountAxis}
              </th>
              {columns.map((r, j) => (
                <th key={j} scope="col" className="px-3 py-2 text-right font-medium">
                  {r === null ? "—" : PERCENT_AXIS.format(r)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {growth_rates.map((g, i) => (
              <tr key={i} className="border-b border-black/5 last:border-0 dark:border-white/5">
                <th scope="row" className="px-3 py-1.5 text-left font-medium">
                  {PERCENT_AXIS.format(g)}
                </th>
                {columns.map((_, j) => {
                  const id = `sensitivity:${i}:${j}`;
                  const cell = result.metrics[id];
                  const isBase = i === center && j === center;
                  const ok = cell?.status === "ok" && cell.value !== null;
                  return (
                    <td
                      key={j}
                      data-metric-value={id}
                      data-status={cell?.status ?? "pending"}
                      title={ok ? undefined : (cell?.reason ?? undefined)}
                      className={`px-3 py-1.5 text-right font-mono tabular-nums ${
                        isBase ? "bg-black/5 font-semibold dark:bg-white/10" : ""
                      } ${ok ? "" : "text-black/40 dark:text-white/40"}`}
                    >
                      {ok ? formatMoneyValue(cell.value as number, cell.unit) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MetricExplainer explainer={v.metrics.sensitivity} />
    </section>
  );
}

function FcfTable({ result }: { result: ValuationResult }) {
  const v = getMessages().valuation;
  const history = result.series.historical_fcf?.points ?? [];
  const forecast = result.series.projected_fcf?.status === "ok" ? result.series.projected_fcf.points : [];
  const rows = [
    ...history.map((p) => ({ key: `h${p.x}`, year: `${v.fcfTable.historical} ${String(p.x)}`, y: p.y })),
    ...forecast.map((p) => ({ key: `f${p.x}`, year: `${v.fcfTable.forecast} +${String(p.x)}`, y: p.y })),
  ];
  return (
    <section data-testid="fcf" aria-labelledby="fcf-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="fcf-heading" className="text-lg font-semibold">
          {v.sections.fcf}
        </h2>
        <ExportCsvButton
          label={v.sections.fcf}
          filename={csvFilename("valuation", "free-cash-flow", result.company.ticker)}
          demo={result.source.is_demo}
          table={{ columns: [v.fcfTable.year, v.fcfTable.value], rows: rows.map((row) => [row.year, row.y]) }}
        />
      </div>
      <div className="mt-2 overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
        <table aria-labelledby="fcf-heading" className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-black/10 dark:border-white/10">
              <th scope="col" className="px-3 py-2 text-left font-medium">
                {v.fcfTable.year}
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                {v.fcfTable.value}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-black/5 last:border-0 dark:border-white/5">
                <th scope="row" className="px-3 py-1.5 text-left font-normal">
                  {row.year}
                </th>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                  {row.y === null ? v.notReported : formatMoneyValue(row.y, "currency")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MetricExplainer explainer={v.metrics.fcf} />
    </section>
  );
}

export function ValuationCalculator() {
  const t = getMessages();
  const v = t.valuation;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const { ticker: linkedTicker, ...initialForm } = initial;
  const initialTicker = linkedTicker.trim().toUpperCase() || DEFAULT_TICKER;
  const [ticker, setTicker] = useState(initialTicker);
  // Only a submitted ticker is fetched (typing doesn't call EDGAR); assumptions update live.
  const [query, setQuery] = useState(initialTicker);
  const [form, setForm] = useState<Form>(initialForm);
  const providers = useMyDataProviders();
  const [chosen, setChosen] = useState<PriceSource>(DEMO_SOURCE);
  // A provider whose key is gone falls back to Demo (a typed-in price only).
  const priceSource: PriceSource = chosen !== DEMO_SOURCE && !providers.includes(chosen) ? DEMO_SOURCE : chosen;
  const { result, fieldErrors, error, pending, run } = useCompute(
    "/valuation/dcf",
    toRequest(query, form, priceSource),
  );
  const valuation = result as ValuationResult | null;
  const m = valuation?.metrics;
  const set = (field: NumberFieldId) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next = ticker.trim().toUpperCase();
    share({ ticker: next, ...form });
    if (next === query) run();
    else setQuery(next);
  }

  function field(name: NumberFieldId) {
    const input = v.inputs[name];
    return (
      <div key={name}>
        <NumberField
          name={name}
          label={input.label}
          hint={
            name === "share_price" && priceSource !== DEMO_SOURCE
              ? v.sharePriceMyDataHint(PROVIDER_NAMES[priceSource])
              : input.hint
          }
          value={form[name]}
          onChange={set(name)}
          error={fieldErrors[name]}
          step={name === "forecast_years" ? "1" : "any"}
        />
        <MetricExplainer explainer={input.explainer} />
      </div>
    );
  }

  return (
    <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-8">
        <form onSubmit={onSubmit} noValidate aria-labelledby="valuation-inputs" className="min-w-0 space-y-6">
          <h2 id="valuation-inputs" className="sr-only">
            {v.inputsHeading}
          </h2>
          <fieldset className="space-y-3">
            <legend className="text-lg font-semibold">{v.sections.company}</legend>
            <DataModeToggle providers={providers} value={priceSource} onChange={setChosen} />
            <div>
              <TextField
                name="ticker"
                label={v.inputs.ticker.label}
                hint={v.inputs.ticker.hint}
                value={ticker}
                onChange={setTicker}
                error={fieldErrors.ticker}
              />
              <MetricExplainer explainer={v.inputs.ticker.explainer} />
            </div>
            <button
              type="submit"
              className="w-full rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
            >
              {v.submit}
            </button>
          </fieldset>
          <fieldset className="space-y-3">
            <legend className="text-lg font-semibold">{v.sections.dcf}</legend>
            {DCF_FIELDS.map(field)}
          </fieldset>
          <fieldset className="space-y-3">
            <legend className="text-lg font-semibold">{v.sections.wacc}</legend>
            {WACC_FIELDS.map(field)}
          </fieldset>
        </form>
        <SavedAssumptions
          ticker={query}
          current={() => toAssumptions(form)}
          onLoad={(saved) => setForm(fromAssumptions(saved))}
        />
      </div>

      <section data-testid="results" aria-label="Results" aria-busy={pending} className="min-w-0 space-y-6">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {valuation ? (
          <>
            <div>
              <h2 className="text-lg font-semibold">{valuation.company.name}</h2>
              <p className="text-sm text-black/60 dark:text-white/60">
                {valuation.company.ticker} · {v.baseYear} {valuation.base_period.label} ·{" "}
                <a href={valuation.base_period.url} target="_blank" rel="noreferrer" className="underline decoration-dotted">
                  {v.filed} {valuation.base_period.filed}
                </a>
              </p>
            </div>
            <div data-testid="market-comparison">
              <h2 className="text-lg font-semibold">{v.sections.market}</h2>
              <div className="mt-2 grid gap-4 sm:grid-cols-2">
                <Card
                  id="share_price"
                  explainer={v.metrics.share_price}
                  values={[{ id: "share_price", result: m?.share_price, note: priceNote(valuation) }]}
                />
                <Card id="market_cap" explainer={v.metrics.market_cap} values={[{ id: "market_cap", result: m?.market_cap }]} />
                <Card
                  id="margin_of_safety"
                  explainer={v.metrics.margin_of_safety}
                  values={[{ id: "margin_of_safety", result: m?.margin_of_safety }]}
                />
              </div>
            </div>
            <div>
              <h2 className="text-lg font-semibold">{v.sections.valuation}</h2>
              <div className="mt-2 grid gap-4 sm:grid-cols-2">
                <Card
                  id="intrinsic_value_per_share"
                  explainer={v.metrics.intrinsic_value_per_share}
                  values={[{ id: "intrinsic_value_per_share", result: m?.intrinsic_value_per_share }]}
                />
                <Card id="equity_value" explainer={v.metrics.equity_value} values={[{ id: "equity_value", result: m?.equity_value }]} />
                <Card
                  id="enterprise_value"
                  explainer={v.metrics.enterprise_value}
                  values={[{ id: "enterprise_value", result: m?.enterprise_value }]}
                />
                <Card
                  id="pv_forecast_fcf"
                  explainer={v.metrics.pv_forecast_fcf}
                  values={[{ id: "pv_forecast_fcf", result: m?.pv_forecast_fcf }]}
                />
                <Card
                  id="pv_terminal_value"
                  explainer={v.metrics.pv_terminal_value}
                  values={[
                    { id: "pv_terminal_value", label: v.labels.presentValue, result: m?.pv_terminal_value },
                    { id: "terminal_value", label: v.labels.atYearN, result: m?.terminal_value },
                  ]}
                />
              </div>
            </div>
            <div>
              <h2 className="text-lg font-semibold">{v.sections.wacc_breakdown}</h2>
              <div className="mt-2 grid gap-4 sm:grid-cols-2">
                <Card
                  id="cost_of_equity"
                  explainer={v.metrics.cost_of_equity}
                  values={[{ id: "cost_of_equity", result: m?.cost_of_equity, note: basisNote(m?.cost_of_equity) }]}
                />
                <Card
                  id="cost_of_debt"
                  explainer={v.metrics.cost_of_debt}
                  values={[
                    { id: "cost_of_debt", label: v.labels.preTax, result: m?.cost_of_debt, note: basisNote(m?.cost_of_debt) },
                    { id: "after_tax_cost_of_debt", label: v.labels.afterTax, result: m?.after_tax_cost_of_debt },
                  ]}
                />
                <Card
                  id="tax_rate"
                  explainer={v.metrics.tax_rate}
                  values={[{ id: "tax_rate", result: m?.tax_rate, note: basisNote(m?.tax_rate) }]}
                />
                <Card
                  id="capital_structure"
                  explainer={v.metrics.capital_structure}
                  values={[
                    { id: "equity_weight", label: v.labels.equity, result: m?.equity_weight },
                    { id: "debt_weight", label: v.labels.debt, result: m?.debt_weight, note: basisNote(m?.debt_weight) },
                  ]}
                />
                <Card id="wacc" explainer={v.metrics.wacc} values={[{ id: "wacc", result: m?.wacc }]} />
                <Card
                  id="discount_rate"
                  explainer={v.metrics.discount_rate}
                  values={[{ id: "discount_rate", result: m?.discount_rate, note: basisNote(m?.discount_rate) }]}
                />
              </div>
            </div>
            <SensitivityTable result={valuation} />
            <div>
              <h2 className="text-lg font-semibold">{v.sections.statementInputs}</h2>
              <div className="mt-2 grid gap-4 sm:grid-cols-2">
                <Card
                  id="free_cash_flow"
                  explainer={v.metrics.free_cash_flow}
                  values={[{ id: "free_cash_flow", result: m?.free_cash_flow }]}
                />
                <Card id="cash" explainer={v.metrics.cash} values={[{ id: "cash", result: m?.cash }]} />
                <Card
                  id="short_term_investments"
                  explainer={v.metrics.short_term_investments}
                  values={[
                    {
                      id: "short_term_investments",
                      result: m?.short_term_investments,
                      note: basisNote(m?.short_term_investments),
                    },
                  ]}
                />
                <Card id="total_debt" explainer={v.metrics.total_debt} values={[{ id: "total_debt", result: m?.total_debt }]} />
                <Card
                  id="shares_outstanding"
                  explainer={v.metrics.shares_outstanding}
                  values={[{ id: "shares_outstanding", result: m?.shares_outstanding }]}
                />
              </div>
            </div>
            <FcfTable result={valuation} />
            <CalculationInfo result={valuation} />
          </>
        ) : (
          !error && <p className="text-sm text-black/60 dark:text-white/60">{v.loading}</p>
        )}
      </section>
    </div>
  );
}
