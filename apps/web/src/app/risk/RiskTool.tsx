"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { DataModeToggle } from "@/components/DataModeToggle";
import { DemoBadge } from "@/components/DemoBadge";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { LineChart, type ChartMarker, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { FactorFiles } from "./FactorFiles";
import type { MetricResult, SeriesResult } from "@/lib/envelope";
import { csvFilename } from "@/lib/csv";
import { formatChartDate, formatChartPercent, formatCount, formatValue } from "@/lib/format";
import { DEMO_SOURCE, useMyDataProviders, type PriceSource } from "@/lib/myData";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";

// Metric ids are "<metric>:<ticker>", series ids "drawdown:<ticker>".
// Cards are grouped by section; the order within a group is the display order.
const METRIC_GROUPS = {
  metrics: ["annualized_return", "annualized_volatility", "max_drawdown"],
  tail: ["var", "cvar", "parametric_var", "parametric_cvar", "cornish_fisher_var", "cornish_fisher_cvar"],
  riskAdjusted: ["sharpe", "sortino", "treynor", "information_ratio"],
  benchmark: ["beta", "alpha", "upside_capture", "downside_capture"],
  ff3: ["ff3_alpha", "ff3_market", "ff3_smb", "ff3_hml", "ff3_r_squared"],
  carhart: ["carhart_alpha", "carhart_market", "carhart_smb", "carhart_hml", "carhart_mom", "carhart_r_squared"],
} as const;

/** The factor sections; their values carry a t-statistic or an observation count. */
const FACTOR_GROUPS: ReadonlySet<string> = new Set(["ff3", "carhart"]);

type MetricId = (typeof METRIC_GROUPS)[keyof typeof METRIC_GROUPS][number];
const ALL_METRICS: MetricId[] = Object.values(METRIC_GROUPS).flat();

// confidence and risk_free_rate are kept in percent; the API takes decimals.
type Form = {
  tickers: string;
  benchmark: string;
  start: string;
  end: string;
  confidence: string;
  risk_free_rate: string;
};

const DEMO_DEFAULTS: Form = {
  tickers: "DEMO-A, DEMO-B, DEMO-D",
  benchmark: "DEMO-MKT",
  start: "2021-01-01",
  end: "2025-12-31",
  confidence: "95",
  risk_free_rate: "0",
};

/** The first switch to My data starts from real tickers; each mode keeps its own inputs. */
const MY_DATA_DEFAULTS: Form = { ...DEMO_DEFAULTS, tickers: "AAPL, MSFT", benchmark: "SPY" };

const defaultsFor = (source: PriceSource): Form => (source === DEMO_SOURCE ? DEMO_DEFAULTS : MY_DATA_DEFAULTS);

// Shareable links: `/risk?tickers=DEMO-A,DEMO-D&start=2022-01-01`, one param per field.
// Demo inputs only: My data needs the visitor's own key, so a link never carries it.
const URL_CODEC = fieldsCodec(DEMO_DEFAULTS);

function percentToDecimal(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n / 100 : null;
}

/** Empty inputs go to the API as null so it reports the field. */
function toRequest(form: Form, source: PriceSource) {
  return {
    source,
    tickers: form.tickers
      .split(/[\s,]+/)
      .map((t) => t.trim())
      .filter(Boolean),
    benchmark: form.benchmark.trim() || null,
    start: form.start || null,
    end: form.end || null,
    confidence: percentToDecimal(form.confidence),
    risk_free_rate: percentToDecimal(form.risk_free_rate),
  };
}

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

function dateMarker(result: MetricResult | undefined, key: string, label: string): ChartMarker[] {
  const iso = result?.status === "ok" ? result.details[key] : null;
  return typeof iso === "string" ? [{ x: Date.parse(iso), label }] : [];
}

type FactorCopy = ReturnType<typeof getMessages>["risk"]["factors"];

/** The line under a factor regression value: its t-statistic, or for R² the days (or months) used. */
function factorNote(result: MetricResult | undefined, copy: FactorCopy): string | undefined {
  if (result?.status !== "ok") return undefined;
  const { t_stat: t, observations: n, frequency } = result.details;
  if (typeof n === "number") return `${formatCount(n)} ${copy.observations[frequency === "monthly" ? "monthly" : "daily"]}`;
  if (typeof t === "number") return `${copy.tStat} ${formatValue(t, "ratio")}`;
  return copy.exactFit;
}

/** Where the factors came from, from the first factor result that names it. */
function factorSource(result: { metrics: Record<string, MetricResult> } | null | undefined): string | undefined {
  const named = Object.values(result?.metrics ?? {}).find((m) => typeof m.details.factor_source === "string");
  return named?.details.factor_source as string | undefined;
}

export function RiskTool() {
  const t = getMessages();
  const r = t.risk;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const providers = useMyDataProviders();
  const [chosen, setChosen] = useState<PriceSource>(DEMO_SOURCE);
  // A provider whose key is gone falls back to demo data.
  const source: PriceSource = chosen !== DEMO_SOURCE && !providers.includes(chosen) ? DEMO_SOURCE : chosen;
  const [forms, setForms] = useState<Partial<Record<PriceSource, Form>>>(() => ({ [DEMO_SOURCE]: initial }));
  const form = forms[source] ?? defaultsFor(source);
  const [chartTicker, setChartTicker] = useState<string | null>(null);
  const { result, fieldErrors, error, run } = useCompute<string, string>("/risk/metrics", toRequest(form, source));
  const set = (field: keyof Form) => (value: string) =>
    setForms((all) => ({ ...all, [source]: { ...(all[source] ?? defaultsFor(source)), [field]: value } }));
  const hints = source === DEMO_SOURCE ? r.inputs : { ...r.inputs, ...r.myDataInputs };

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (source === DEMO_SOURCE) share(form);
    run();
  }

  const params = result?.meta.parameters as { tickers: string[]; benchmark: string } | undefined;
  const benchmark = params?.benchmark ?? "";
  const symbols = params ? [...new Set([...params.tickers, benchmark])] : [];
  const label = (ticker: string) => (ticker === benchmark ? `${ticker} ${r.benchmarkSuffix}` : ticker);

  const selected = chartTicker && symbols.includes(chartTicker) ? chartTicker : symbols[0];
  const mdd = selected ? result?.metrics[`max_drawdown:${selected}`] : undefined;
  const chartSeries: ChartSeries[] =
    result && selected
      ? [
          { id: selected, label: selected, points: chartPoints(result.series[`drawdown:${selected}`]), color: "#dc2626" },
          ...(selected !== benchmark
            ? [
                {
                  id: benchmark,
                  label: label(benchmark),
                  points: chartPoints(result.series[`drawdown:${benchmark}`]),
                  color: "#64748b",
                  dashed: true,
                },
              ]
            : []),
        ]
      : [];
  const markers = [...dateMarker(mdd, "peak", r.chart.peak), ...dateMarker(mdd, "trough", r.chart.trough)];
  const factorSourceId = factorSource(result);
  const factorSourceText =
    factorSourceId && factorSourceId in r.factors.source
      ? r.factors.source[factorSourceId as keyof typeof r.factors.source]
      : undefined;

  return (
    <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <form onSubmit={onSubmit} noValidate aria-labelledby="risk-inputs" className="min-w-0 space-y-4">
        <h2 id="risk-inputs" className="text-lg font-semibold">
          {r.inputsHeading}
        </h2>
        <DataModeToggle providers={providers} value={source} onChange={setChosen} />
        {source !== DEMO_SOURCE && <FactorFiles onChange={run} />}
        <TextField
          name="tickers"
          label={r.inputs.tickers.label}
          hint={hints.tickers.hint}
          value={form.tickers}
          onChange={set("tickers")}
          error={fieldErrors.tickers}
        />
        <TextField
          name="benchmark"
          label={r.inputs.benchmark.label}
          hint={hints.benchmark.hint}
          value={form.benchmark}
          onChange={set("benchmark")}
          error={fieldErrors.benchmark}
        />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
          <TextField
            type="date"
            name="start"
            label={r.inputs.start.label}
            hint={hints.start.hint}
            value={form.start}
            onChange={set("start")}
            error={fieldErrors.start}
          />
          <TextField
            type="date"
            name="end"
            label={r.inputs.end.label}
            hint={hints.end.hint}
            value={form.end}
            onChange={set("end")}
            error={fieldErrors.end}
          />
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
          <NumberField
            name="confidence"
            label={r.inputs.confidence.label}
            hint={hints.confidence.hint}
            value={form.confidence}
            onChange={set("confidence")}
            error={fieldErrors.confidence}
          />
          <NumberField
            name="risk_free_rate"
            label={r.inputs.risk_free_rate.label}
            hint={hints.risk_free_rate.hint}
            value={form.risk_free_rate}
            onChange={set("risk_free_rate")}
            error={fieldErrors.risk_free_rate}
          />
        </div>
        <button
          type="submit"
          className="w-full rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {r.submit}
        </button>
      </form>

      <section data-testid="results" aria-label="Results" className="min-w-0 space-y-6">
        <DemoBadge source={result?.source} />
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        {result && params && (
          <div className="flex justify-end">
            <ExportCsvButton
              label={r.csvLabel}
              filename={csvFilename("risk", "metrics", params.tickers.join("_"))}
              demo={result.source.is_demo}
              table={{
                columns: [t.common.csv.ticker, ...ALL_METRICS.map((id) => r.metrics[id].name)],
                rows: symbols.map((ticker) => [ticker, ...ALL_METRICS.map((id) => result.metrics[`${id}:${ticker}`])]),
              }}
            />
          </div>
        )}
        {(Object.keys(METRIC_GROUPS) as (keyof typeof METRIC_GROUPS)[]).map((group) => (
          <div key={group}>
            <h2 className="text-lg font-semibold">{r.sections[group]}</h2>
            {group === "ff3" && factorSourceText && (
              <p data-testid="factor-source" className="mt-1 text-sm text-black/70 dark:text-white/70">
                {factorSourceText}
              </p>
            )}
            <div className="mt-2 grid gap-4 xl:grid-cols-3">
              {METRIC_GROUPS[group].map((id: MetricId) => (
                <MetricCard
                  key={id}
                  id={id}
                  explainer={r.metrics[id]}
                  values={
                    symbols.length
                      ? symbols.map((ticker) => {
                          const value = result?.metrics[`${id}:${ticker}`];
                          return {
                            id: `${id}:${ticker}`,
                            label: label(ticker),
                            result: value,
                            note: FACTOR_GROUPS.has(group) ? factorNote(value, r.factors) : undefined,
                          };
                        })
                      : [{ id: `${id}:pending`, result: undefined }]
                  }
                />
              ))}
            </div>
          </div>
        ))}
        <div>
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h2 className="text-lg font-semibold">{r.sections.chart}</h2>
            {symbols.length > 0 && (
              <label className="text-sm">
                <span className="mr-2">{r.chart.select}</span>
                <select
                  value={selected}
                  onChange={(e) => setChartTicker(e.target.value)}
                  className="rounded-md border border-black/20 px-2 py-1 font-mono dark:border-white/20 dark:bg-white/5"
                >
                  {symbols.map((ticker) => (
                    <option key={ticker} value={ticker}>
                      {label(ticker)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="mt-2">
            {result && (
              <LineChart
                label={r.chart.label}
                series={chartSeries}
                xLabel={r.chart.x}
                formatX={formatChartDate}
                formatY={formatChartPercent}
                markers={markers}
              />
            )}
          </div>
          {mdd?.status === "ok" && mdd.value !== null && (
            <p data-testid="drawdown-window" className="mt-1 text-sm text-black/70 dark:text-white/70">
              {r.chart.window} ({selected}): {formatValue(mdd.value, mdd.unit)} {r.chart.from} {mdd.details.peak}{" "}
              {r.chart.to} {mdd.details.trough};{" "}
              {mdd.details.recovery ? `${r.chart.recovered} ${mdd.details.recovery}` : r.chart.notRecovered}.
            </p>
          )}
        </div>
        {result && <CalculationInfo result={result} />}
      </section>
    </div>
  );
}
