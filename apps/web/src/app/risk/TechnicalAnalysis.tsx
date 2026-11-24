"use client";

import { useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricExplainer } from "@/components/MetricExplainer";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import type { SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartNumber } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { fieldsCodec, useUrlInputs, writeUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { INK, REFERENCE, series } from "@/lib/chartColors";

/** The Risk & Performance selection the panel follows (from the last good `/risk/metrics` result). */
export type RiskSelection = { tickers: string[]; benchmark: string; start: string; end: string; source: string };

type IndicatorId = "sma" | "ema" | "bollinger" | "rsi" | "macd";
type SeriesId =
  | "price"
  | "sma"
  | "ema"
  | "bollinger_upper"
  | "bollinger_middle"
  | "bollinger_lower"
  | "rsi"
  | "macd"
  | "macd_signal"
  | "macd_histogram";

// Each parameter input is named "<indicator>_<request field>", so the API's
// "macd.slow" error maps onto the "macd_slow" input.
const PARAMS = {
  sma: ["window"],
  ema: ["window"],
  bollinger: ["window", "width"],
  rsi: ["window"],
  macd: ["fast", "slow", "signal"],
} as const satisfies Record<IndicatorId, readonly string[]>;

type ParamName = { [K in IndicatorId]: `${K}_${(typeof PARAMS)[K][number]}` }[IndicatorId];
type Form = { on: Record<IndicatorId, boolean>; values: Record<ParamName, string> };

const DEFAULTS: Form = {
  on: { sma: true, ema: false, bollinger: false, rsi: true, macd: false },
  values: {
    sma_window: "50",
    ema_window: "20",
    bollinger_window: "20",
    bollinger_width: "2",
    rsi_window: "14",
    macd_fast: "12",
    macd_slow: "26",
    macd_signal: "9",
  },
};

const INDICATORS = Object.keys(PARAMS) as IndicatorId[];
const VALUES_CODEC = fieldsCodec(DEFAULTS.values);

// Shareable links: `/risk?...&indicators=sma,macd&sma_window=50&macd_fast=8`: which
// indicators are on (`indicators=` for none) and every parameter. Written on every
// change, since the panel has no submit button.
const URL_CODEC: UrlCodec<Form> = {
  keys: ["indicators", ...VALUES_CODEC.keys],
  read(params) {
    const raw = params.get("indicators");
    const listed = raw === null ? null : new Set(raw.split(",").map((id) => id.trim()));
    const on = listed
      ? (Object.fromEntries(INDICATORS.map((id) => [id, listed.has(id)])) as Form["on"])
      : DEFAULTS.on;
    return { on, values: VALUES_CODEC.read(params) };
  },
  write: (form) => ({
    indicators: INDICATORS.filter((id) => form.on[id]).join(","),
    ...VALUES_CODEC.write(form.values),
  }),
};
/** This panel's query params: a link with any of them and no `tab=` opens its tab. */
export const TECHNICAL_PARAMS = URL_CODEC.keys;

const COLORS: Record<SeriesId, string> = {
  price: INK,
  sma: series(0),
  ema: series(1),
  bollinger_upper: series(2),
  bollinger_middle: series(3),
  bollinger_lower: series(2),
  rsi: series(4),
  macd: series(0),
  macd_signal: series(1),
  macd_histogram: REFERENCE,
};

function toNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** Off indicators are sent as null; empty or non-numeric inputs as null so the API reports the field. */
function toRequest(ticker: string, selection: RiskSelection, form: Form) {
  const body: Record<string, unknown> = { ticker, start: selection.start, end: selection.end, source: selection.source };
  for (const id of Object.keys(PARAMS) as IndicatorId[]) {
    body[id] = form.on[id]
      ? Object.fromEntries(
          PARAMS[id].map((p) => [p, toNumber(form.values[`${id}_${p}` as ParamName])]),
        )
      : null;
  }
  return body;
}

function points(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/** Indicator overlays on one ticker's price, RSI and MACD panels, and the correlation heatmap. */
export function TechnicalAnalysis({ selection }: { selection: RiskSelection }) {
  const t = getMessages().riskTechnical;
  const common = getMessages().common;
  const symbols = [...new Set([...selection.tickers, selection.benchmark])];
  const [chosen, setChosen] = useState<string | null>(null);
  const ticker = chosen && symbols.includes(chosen) ? chosen : symbols[0];
  const { initial } = useUrlInputs(URL_CODEC);
  const [form, setFormState] = useState<Form>(initial);
  const setForm = (update: (f: Form) => Form) => {
    const next = update(form);
    setFormState(next);
    writeUrlInputs(URL_CODEC, next);
  };
  const { result, fieldErrors, error } = useCompute<never, SeriesId>(
    "/risk/indicators",
    toRequest(ticker, selection, form),
  );
  const errorFor = (name: ParamName) => fieldErrors[name.replace("_", ".")];
  const toggle = (id: IndicatorId) => (checked: boolean) =>
    setForm((f) => ({ ...f, on: { ...f.on, [id]: checked } }));
  const setValue = (name: ParamName) => (value: string) =>
    setForm((f) => ({ ...f, values: { ...f.values, [name]: value } }));

  // Labels follow the parameters of the result on screen, not the inputs being typed.
  const shown = result?.meta.parameters as Record<IndicatorId, Record<string, number> | null> & { ticker: string };
  const line = (id: SeriesId, label: string, dashed = false): ChartSeries[] =>
    result?.series[id] ? [{ id, label, points: points(result.series[id]), color: COLORS[id], dashed }] : [];
  const s = t.series;
  const priceSeries = shown
    ? [
        ...line("price", `${shown.ticker} ${s.price}`),
        ...line("sma", `${s.sma} (${shown.sma?.window})`),
        ...line("ema", `${s.ema} (${shown.ema?.window})`),
        ...line("bollinger_upper", s.bollinger_upper, true),
        ...line("bollinger_middle", s.bollinger_middle, true),
        ...line("bollinger_lower", s.bollinger_lower, true),
      ]
    : [];
  const rsiSeries = shown ? line("rsi", `${s.rsi} (${shown.rsi?.window})`) : [];
  const macdSeries = shown
    ? [...line("macd", s.macd), ...line("macd_signal", s.macd_signal), ...line("macd_histogram", s.macd_histogram, true)]
    : [];

  const checkbox = (id: IndicatorId) => (
    <label className="flex items-center gap-2 text-sm font-medium">
      <input type="checkbox" checked={form.on[id]} onChange={(e) => toggle(id)(e.target.checked)} />
      {t.toggles[id]}
    </label>
  );
  const params = (id: IndicatorId) =>
    form.on[id] && (
      <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {PARAMS[id].map((p) => {
          const name = `${id}_${p}` as ParamName;
          return (
            <NumberField
              key={name}
              name={name}
              label={t.inputs[name]}
              value={form.values[name]}
              onChange={setValue(name)}
              error={errorFor(name)}
            />
          );
        })}
      </div>
    );

  return (
    <div data-testid="technical-analysis" className="space-y-6">
      <div>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-xl">{t.heading}</h2>
          <label className="text-sm">
            <span className="mr-2">{t.select}</span>
            <select
              value={ticker}
              onChange={(e) => setChosen(e.target.value)}
              className="rounded-card border border-muted px-2 py-1 tabular-nums"
            >
              {symbols.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="mt-1 text-sm text-ink-2">{t.intro}</p>
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? common.errors.invalidHeading : common.errors.heading}
            message={error}
          />
        )}
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <fieldset className="min-w-0">
            <div className="flex flex-wrap gap-4">
              {checkbox("sma")}
              {checkbox("ema")}
            </div>
            {params("sma")}
            {params("ema")}
            <MetricExplainer explainer={t.explainers.movingAverages} />
          </fieldset>
          <fieldset className="min-w-0">
            {checkbox("bollinger")}
            {params("bollinger")}
            <MetricExplainer explainer={t.explainers.bollinger} />
          </fieldset>
          <fieldset className="min-w-0">
            {checkbox("rsi")}
            {params("rsi")}
            <MetricExplainer explainer={t.explainers.rsi} />
          </fieldset>
          <fieldset className="min-w-0">
            {checkbox("macd")}
            {params("macd")}
            <MetricExplainer explainer={t.explainers.macd} />
          </fieldset>
        </div>
      </div>

      {shown && (
        <div className="space-y-4">
          <div data-testid="indicator-legend-price">
            <LineChart
              label={`${t.charts.price} ${shown.ticker}`}
              series={priceSeries}
              xLabel={t.dateLabel}
              formatX={formatChartDate}
              formatY={formatChartNumber}
            />
          </div>
          {rsiSeries.length > 0 && (
            <LineChart
              label={`${t.charts.rsi} ${shown.ticker}`}
              series={rsiSeries}
              xLabel={t.dateLabel}
              formatX={formatChartDate}
              formatY={formatChartNumber}
              height={180}
            />
          )}
          {macdSeries.length > 0 && (
            <LineChart
              label={`${t.charts.macd} ${shown.ticker}`}
              series={macdSeries}
              xLabel={t.dateLabel}
              formatX={formatChartDate}
              formatY={formatChartNumber}
              height={200}
            />
          )}
        </div>
      )}

      <CorrelationHeatmap selection={selection} />
    </div>
  );
}
