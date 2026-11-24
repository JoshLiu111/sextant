"use client";

import { useState, type FormEvent } from "react";
import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice, FieldError } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import { formatChartNumber } from "@/lib/format";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { STICKY_INPUTS, toolColumns } from "@/lib/layout";
import { chartPoints, isPercentField, toNumber } from "./form";
import { series } from "@/lib/chartColors";

type MetricId =
  | "call_price"
  | "put_price"
  | "call_delta"
  | "put_delta"
  | "gamma"
  | "vega"
  | "call_theta"
  | "put_theta"
  | "call_rho"
  | "put_rho"
  | "implied_volatility";
type SeriesId = "payoff_at_expiry" | "theoretical_value";
type OptionType = "call" | "put";

// Form state uses display units (percent); the request model uses decimals.
type Form = {
  spot: string;
  strike: string;
  time_to_expiry: string;
  volatility: string;
  risk_free_rate: string;
  dividend_yield: string;
  option_type: OptionType;
  market_price: string;
};
type NumericField = Exclude<keyof Form, "option_type">;

const DEFAULTS: Form = {
  spot: "100",
  strike: "100",
  time_to_expiry: "1",
  volatility: "20",
  risk_free_rate: "5",
  dividend_yield: "0",
  option_type: "call",
  market_price: "",
};

// Shareable links: `/options?spot=110&volatility=30`, one param per field.
const URL_CODEC = fieldsCodec(DEFAULTS);

const NUMERIC_FIELDS: NumericField[] = [
  "spot",
  "strike",
  "time_to_expiry",
  "volatility",
  "risk_free_rate",
  "dividend_yield",
];

function toRequest(form: Form) {
  const body: Record<string, unknown> = { option_type: form.option_type };
  for (const field of NUMERIC_FIELDS) body[field] = toNumber(form[field], isPercentField(field));
  body.market_price = toNumber(form.market_price);
  return body;
}

export function OptionsCalculator() {
  const t = getMessages();
  const o = t.options;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [form, setForm] = useState<Form>(initial);
  const { result, fieldErrors, error, run } = useCompute<MetricId, SeriesId>("/options/price", toRequest(form));
  const m = result?.metrics;
  const set = (field: keyof Form) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share(form);
    run();
  }

  const chartSeries: ChartSeries[] = result
    ? [
        {
          id: "payoff_at_expiry",
          label: o.chart.payoff,
          points: chartPoints(result.series.payoff_at_expiry),
          color: series(0),
        },
        {
          id: "theoretical_value",
          label: o.chart.value,
          points: chartPoints(result.series.theoretical_value),
          color: series(1),
          dashed: true,
        },
      ]
    : [];
  const chartType = (result?.meta.parameters.option_type as OptionType | undefined) ?? form.option_type;
  const chartStrike = Number(result?.meta.parameters.strike);
  const chartSpot = Number(result?.meta.parameters.spot);

  return (
    <div className={`mt-6 ${toolColumns("20rem")}`}>
      <form onSubmit={onSubmit} noValidate aria-labelledby="options-inputs" className={`${STICKY_INPUTS} space-y-4`}>
        <h2 id="options-inputs" className="text-xl">
          {o.inputsHeading}
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
          {NUMERIC_FIELDS.map((field) => (
            <NumberField
              key={field}
              name={field}
              label={o.inputs[field].label}
              hint={o.inputs[field].hint}
              value={form[field]}
              onChange={set(field)}
              error={fieldErrors[field]}
            />
          ))}
        </div>
        <div>
          <label htmlFor="input-option_type" className="label">
            {o.inputs.option_type.label}
          </label>
          <select
            id="input-option_type"
            name="option_type"
            value={form.option_type}
            onChange={(e) => set("option_type")(e.target.value)}
            className="field mt-1"
          >
            <option value="call">{o.optionTypes.call}</option>
            <option value="put">{o.optionTypes.put}</option>
          </select>
          <p className="hint mt-1">{o.inputs.option_type.hint}</p>
          <FieldError name="option_type" message={fieldErrors.option_type} />
        </div>
        <NumberField
          name="market_price"
          label={o.inputs.market_price.label}
          hint={o.inputs.market_price.hint}
          value={form.market_price}
          onChange={set("market_price")}
          error={fieldErrors.market_price}
        />
        <button
          type="submit"
          className="btn btn-primary w-full"
        >
          {o.submit}
        </button>
      </form>

      <section data-testid="results" aria-label="Results" className="min-w-0 space-y-6">
        {error && (
          <ErrorNotice
            title={Object.keys(fieldErrors).length ? t.common.errors.invalidHeading : t.common.errors.heading}
            message={error}
          />
        )}
        <div>
          <h2 className="text-xl">{o.sections.prices}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-2">
            <MetricCard id="call_price" explainer={o.metrics.call_price} values={[{ id: "call_price", result: m?.call_price }]} />
            <MetricCard id="put_price" explainer={o.metrics.put_price} values={[{ id: "put_price", result: m?.put_price }]} />
          </div>
        </div>
        <div>
          <h2 className="text-xl">{o.sections.greeks}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <MetricCard
              id="delta"
              explainer={o.metrics.delta}
              values={[
                { id: "call_delta", label: o.optionTypes.call, result: m?.call_delta },
                { id: "put_delta", label: o.optionTypes.put, result: m?.put_delta },
              ]}
            />
            <MetricCard id="gamma" explainer={o.metrics.gamma} values={[{ id: "gamma", result: m?.gamma }]} />
            <MetricCard id="vega" explainer={o.metrics.vega} values={[{ id: "vega", result: m?.vega }]} />
            <MetricCard
              id="theta"
              explainer={o.metrics.theta}
              values={[
                { id: "call_theta", label: o.optionTypes.call, result: m?.call_theta },
                { id: "put_theta", label: o.optionTypes.put, result: m?.put_theta },
              ]}
            />
            <MetricCard
              id="rho"
              explainer={o.metrics.rho}
              values={[
                { id: "call_rho", label: o.optionTypes.call, result: m?.call_rho },
                { id: "put_rho", label: o.optionTypes.put, result: m?.put_rho },
              ]}
            />
          </div>
        </div>
        <div>
          <h2 className="text-xl">{o.sections.iv}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-2">
            <MetricCard
              id="implied_volatility"
              explainer={o.metrics.implied_volatility}
              values={[
                {
                  id: "implied_volatility",
                  label: o.optionTypes[chartType],
                  result: m?.implied_volatility,
                },
              ]}
            />
          </div>
        </div>
        <div>
          <h2 className="text-xl">
            {o.sections.chart} ({o.optionTypes[chartType]})
          </h2>
          <div className="mt-2">
            {result && (
              <LineChart
                label={o.chart.label}
                series={chartSeries}
                xLabel={o.chart.x}
                formatX={formatChartNumber}
                formatY={formatChartNumber}
                markers={[
                  { x: chartStrike, label: o.chart.strike },
                  ...(chartSpot !== chartStrike ? [{ x: chartSpot, label: o.chart.spot }] : []),
                ]}
              />
            )}
          </div>
        </div>
        {result && <CalculationInfo result={result} />}
        {result && <AiExplain tool="options" result={result} />}
      </section>
    </div>
  );
}
