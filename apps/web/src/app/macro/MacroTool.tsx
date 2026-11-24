"use client";

import { useState, type FormEvent } from "react";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { fieldsCodec, useUrlInputs } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { CustomSeries } from "./CustomSeries";
import { MacroDashboard, type IndicatorMetricId, type IndicatorSeriesId } from "./MacroDashboard";
import { TreasuryRates, type RatesMetricId, type RatesSeriesId } from "./TreasuryRates";

// One input, the start of the chart history, shared by both sections. Blank
// sends no start, so each endpoint uses its own default (FRED 2015, Treasury 2018).
type Form = { start: string };
const DEFAULTS: Form = { start: "" };
// Shareable links: `/macro?start=2020-01-01`.
const URL_CODEC = fieldsCodec(DEFAULTS);

function toRequest(form: Form): { start?: string } {
  return form.start.trim() ? { start: form.start.trim() } : {};
}

export function MacroTool() {
  const t = getMessages();
  const m = t.macro;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [form, setForm] = useState<Form>(initial);
  // Only a submitted range is fetched: each change refetches every series.
  const [query, setQuery] = useState(() => toRequest(initial));
  const indicators = useCompute<IndicatorMetricId, IndicatorSeriesId>("/macro/indicators", query);
  const rates = useCompute<RatesMetricId, RatesSeriesId>("/macro/rates", query);
  const startError = indicators.fieldErrors.start ?? rates.fieldErrors.start;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share(form);
    const next = toRequest(form);
    if (JSON.stringify(next) === JSON.stringify(query)) {
      indicators.run();
      rates.run();
    } else setQuery(next);
  }

  return (
    <>
      <form onSubmit={onSubmit} noValidate aria-labelledby="macro-inputs" className="mt-6 flex flex-wrap items-start gap-4">
        <h3 id="macro-inputs" className="sr-only">
          {m.inputsHeading}
        </h3>
        <div className="w-full max-w-sm">
          <TextField
            type="date"
            name="start"
            label={m.inputs.start.label}
            hint={m.inputs.start.hint}
            value={form.start}
            onChange={(start) => setForm({ start })}
            error={startError}
          />
        </div>
        <button
          type="submit"
          className="mt-6 rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {m.submit}
        </button>
      </form>
      <MacroDashboard result={indicators.result} error={indicators.error} />
      <TreasuryRates result={rates.result} error={rates.error} />
      <CustomSeries start={query.start} />
    </>
  );
}
