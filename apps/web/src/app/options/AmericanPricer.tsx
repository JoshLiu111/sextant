"use client";

import { useState, type FormEvent } from "react";
import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import { formatChartNumber } from "@/lib/format";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { STICKY_INPUTS, toolColumns } from "@/lib/layout";
import { chartPoints, MARKET_DEFAULTS, MARKET_FIELDS, marketRequest, toNumber, type MarketForm } from "./form";
import { REFERENCE, series } from "@/lib/chartColors";

type Kind = "call" | "put";
type MetricId = `american_${Kind}` | `european_${Kind}` | `european_${Kind}_tree` | `${Kind}_early_exercise_premium`;
type SeriesId = `american_${Kind}_by_steps` | `european_${Kind}_tree_by_steps`;

type Form = MarketForm & { strike: string; steps: string };
const DEFAULTS: Form = { ...MARKET_DEFAULTS, strike: "100", steps: "500" };
const FIELDS: (keyof Form)[] = ["spot", "strike", ...MARKET_FIELDS.slice(1), "steps"];
const KINDS: Kind[] = ["call", "put"];

// Shareable links: `/options?tab=american&spot=110&steps=200`, one param per field.
const URL_CODEC = fieldsCodec(DEFAULTS);

function toRequest(form: Form) {
  return { ...marketRequest(form), strike: toNumber(form.strike), steps: toNumber(form.steps) };
}

export function AmericanPricer() {
  const t = getMessages();
  const o = t.options;
  const a = o.american;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [form, setForm] = useState<Form>(initial);
  const [chartKind, setChartKind] = useState<Kind>("put");
  const { result, fieldErrors, error, run } = useCompute<MetricId, SeriesId>("/options/american", toRequest(form));
  const m = result?.metrics;
  const label = (field: keyof Form) => (field === "steps" ? a.inputs.steps : o.inputs[field]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share(form);
    run();
  }

  const americanPoints = chartPoints(result?.series[`american_${chartKind}_by_steps`]);
  const bsValue = m?.[`european_${chartKind}`]?.value;
  const chartSeries: ChartSeries[] = result
    ? [
        { id: "american", label: a.chart.american, points: americanPoints, color: series(0) },
        {
          id: "european_tree",
          label: a.chart.europeanTree,
          points: chartPoints(result.series[`european_${chartKind}_tree_by_steps`]),
          color: series(1),
        },
        {
          id: "bs",
          label: a.chart.bs,
          points: bsValue == null ? [] : americanPoints.map((p) => ({ x: p.x, y: bsValue })),
          color: REFERENCE,
          dashed: true,
        },
      ]
    : [];

  return (
    <div className={`mt-6 ${toolColumns("20rem")}`}>
      <form onSubmit={onSubmit} noValidate aria-labelledby="american-inputs" className={`${STICKY_INPUTS} space-y-4`}>
        <p className="max-w-[55ch] text-sm text-ink-2">{a.intro}</p>
        <h2 id="american-inputs" className="text-xl">
          {o.inputsHeading}
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
          {FIELDS.map((field) => (
            <NumberField
              key={field}
              name={field}
              label={label(field).label}
              hint={label(field).hint}
              value={form[field]}
              onChange={(v) => setForm((f) => ({ ...f, [field]: v }))}
              error={fieldErrors[field]}
              step={field === "steps" ? "1" : undefined}
            />
          ))}
        </div>
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
          <h2 className="text-xl">{a.sections.prices}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-2">
            {(
              [
                ["american", (k: Kind) => `american_${k}`],
                ["european", (k: Kind) => `european_${k}`],
                ["early_exercise_premium", (k: Kind) => `${k}_early_exercise_premium`],
                ["european_tree", (k: Kind) => `european_${k}_tree`],
              ] as const
            ).map(([card, id]) => (
              <MetricCard
                key={card}
                id={card}
                explainer={a.metrics[card]}
                values={KINDS.map((k) => ({
                  id: id(k),
                  label: o.optionTypes[k],
                  result: m?.[id(k) as MetricId],
                }))}
              />
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-xl">{a.sections.chart}</h2>
          <div className="mt-2 flex items-center gap-2">
            <label htmlFor="american-chart-kind" className="text-sm text-muted">
              {a.chart.select}
            </label>{" "}
            <select
              id="american-chart-kind"
              value={chartKind}
              onChange={(e) => setChartKind(e.target.value as Kind)}
              className="field w-auto"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {o.optionTypes[k]}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-2">
            {result && (
              <LineChart
                label={a.chart.label}
                series={chartSeries}
                xLabel={a.chart.x}
                formatX={(x) => String(Math.round(x))}
                formatY={formatChartNumber}
              />
            )}
          </div>
        </div>
        {result && <CalculationInfo result={result} />}
        {result && <AiExplain tool="options-american" result={result} />}
      </section>
    </div>
  );
}
