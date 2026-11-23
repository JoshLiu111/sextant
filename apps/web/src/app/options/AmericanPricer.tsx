"use client";

import { useState, type FormEvent } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import { formatChartNumber } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { chartPoints, MARKET_DEFAULTS, MARKET_FIELDS, marketRequest, toNumber, type MarketForm } from "./form";

type Kind = "call" | "put";
type MetricId = `american_${Kind}` | `european_${Kind}` | `european_${Kind}_tree` | `${Kind}_early_exercise_premium`;
type SeriesId = `american_${Kind}_by_steps` | `european_${Kind}_tree_by_steps`;

type Form = MarketForm & { strike: string; steps: string };
const DEFAULTS: Form = { ...MARKET_DEFAULTS, strike: "100", steps: "500" };
const FIELDS: (keyof Form)[] = ["spot", "strike", ...MARKET_FIELDS.slice(1), "steps"];
const KINDS: Kind[] = ["call", "put"];

function toRequest(form: Form) {
  return { ...marketRequest(form), strike: toNumber(form.strike), steps: toNumber(form.steps) };
}

export function AmericanPricer() {
  const t = getMessages();
  const o = t.options;
  const a = o.american;
  const [form, setForm] = useState<Form>(DEFAULTS);
  const [chartKind, setChartKind] = useState<Kind>("put");
  const { result, fieldErrors, error, run } = useCompute<MetricId, SeriesId>("/options/american", toRequest(form));
  const m = result?.metrics;
  const label = (field: keyof Form) => (field === "steps" ? a.inputs.steps : o.inputs[field]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    run();
  }

  const americanPoints = chartPoints(result?.series[`american_${chartKind}_by_steps`]);
  const bsValue = m?.[`european_${chartKind}`]?.value;
  const chartSeries: ChartSeries[] = result
    ? [
        { id: "american", label: a.chart.american, points: americanPoints, color: "#2563eb" },
        {
          id: "european_tree",
          label: a.chart.europeanTree,
          points: chartPoints(result.series[`european_${chartKind}_tree_by_steps`]),
          color: "#ea580c",
        },
        {
          id: "bs",
          label: a.chart.bs,
          points: bsValue == null ? [] : americanPoints.map((p) => ({ x: p.x, y: bsValue })),
          color: "#6b7280",
          dashed: true,
        },
      ]
    : [];

  return (
    <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <form onSubmit={onSubmit} noValidate aria-labelledby="american-inputs" className="space-y-4">
        <p className="text-sm text-black/70 dark:text-white/70">{a.intro}</p>
        <h2 id="american-inputs" className="text-lg font-semibold">
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
          className="w-full rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
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
          <h2 className="text-lg font-semibold">{a.sections.prices}</h2>
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
          <h2 className="text-lg font-semibold">{a.sections.chart}</h2>
          <div className="mt-2">
            <label htmlFor="american-chart-kind" className="text-sm">
              {a.chart.select}
            </label>{" "}
            <select
              id="american-chart-kind"
              value={chartKind}
              onChange={(e) => setChartKind(e.target.value as Kind)}
              className="rounded-md border border-black/20 px-2 py-1 text-sm dark:border-white/20 dark:bg-white/5"
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
      </section>
    </div>
  );
}
