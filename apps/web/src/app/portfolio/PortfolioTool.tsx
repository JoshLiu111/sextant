"use client";

import { useState, type FormEvent } from "react";
import { DemoBadge } from "@/components/DemoBadge";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { NumberField } from "@/components/NumberField";
import { TextField } from "@/components/TextField";
import { getMessages } from "@/i18n";
import { decodeRows, encodeRows, fieldsCodec, useUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { PortfolioConstruction } from "./PortfolioConstruction";
import { PortfolioResults } from "./PortfolioResults";
import { DEFAULT_HOLDINGS, PRESETS, type HoldingInput, type PresetId } from "./presets";

// Weights, confidence and risk_free_rate are kept in percent; the API takes decimals.
type Form = {
  holdings: HoldingInput[];
  benchmark: string;
  start: string;
  end: string;
  confidence: string;
  risk_free_rate: string;
};

const DEFAULTS: Form = {
  holdings: [...DEFAULT_HOLDINGS],
  benchmark: "DEMO-MKT",
  start: "2021-01-01",
  end: "2025-12-31",
  confidence: "95",
  risk_free_rate: "0",
};

// Shareable links: `/portfolio?holdings=DEMO-C:60,DEMO-E:40&start=2022-01-01`.
// Only these demo inputs go in the URL; saved portfolios never do.
const SETTINGS_CODEC = fieldsCodec({
  benchmark: DEFAULTS.benchmark,
  start: DEFAULTS.start,
  end: DEFAULTS.end,
  confidence: DEFAULTS.confidence,
  risk_free_rate: DEFAULTS.risk_free_rate,
});
const URL_CODEC: UrlCodec<Form> = {
  keys: ["holdings", ...SETTINGS_CODEC.keys],
  read(params) {
    const raw = params.get("holdings");
    const rows = raw === null ? [] : decodeRows(raw, 2);
    const holdings = rows.length ? rows.map(([ticker, weight]) => ({ ticker, weight })) : DEFAULTS.holdings;
    return { holdings, ...SETTINGS_CODEC.read(params) };
  },
  write({ holdings, ...settings }) {
    return { holdings: encodeRows(holdings.map((h) => [h.ticker, h.weight])), ...SETTINGS_CODEC.write(settings) };
  },
};

function percentToDecimal(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n / 100 : null;
}

/** Empty inputs go to the API as null so it reports the field. */
function toRequest(form: Form) {
  return {
    holdings: form.holdings.map((h) => ({ ticker: h.ticker.trim(), weight: percentToDecimal(h.weight) })),
    benchmark: form.benchmark.trim() || null,
    start: form.start || null,
    end: form.end || null,
    confidence: percentToDecimal(form.confidence),
    risk_free_rate: percentToDecimal(form.risk_free_rate),
  };
}

function weightTotal(holdings: HoldingInput[]): string {
  const total = holdings.reduce((sum, h) => sum + (Number(h.weight) || 0), 0);
  return `${Math.round(total * 100) / 100}%`;
}

const inputClass = (error: string | undefined) =>
  `w-full min-w-0 rounded-md border px-3 py-2 font-mono dark:bg-white/5 ${
    error ? "border-red-500" : "border-black/20 dark:border-white/20"
  }`;

export function PortfolioTool() {
  const t = getMessages();
  const p = t.portfolio;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [form, setForm] = useState<Form>(initial);
  const request = toRequest(form);
  const { result, fieldErrors, error, run } = useCompute<string, string>("/portfolio/metrics", request);
  const set = (field: Exclude<keyof Form, "holdings">) => (value: string) => setForm((f) => ({ ...f, [field]: value }));
  const setHoldings = (update: (holdings: HoldingInput[]) => HoldingInput[]) =>
    setForm((f) => ({ ...f, holdings: update(f.holdings) }));
  const setHolding = (index: number, field: keyof HoldingInput) => (value: string) =>
    setHoldings((hs) => hs.map((h, i) => (i === index ? { ...h, [field]: value } : h)));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share(form);
    run();
  }

  return (
    <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <form onSubmit={onSubmit} noValidate aria-labelledby="portfolio-inputs" className="min-w-0 space-y-4">
        <h2 id="portfolio-inputs" className="text-lg font-semibold">
          {p.inputsHeading}
        </h2>

        <fieldset className="min-w-0">
          <legend className="text-sm font-medium">{p.presets.heading}</legend>
          <p className="mt-1 text-xs text-black/50 dark:text-white/50">{p.presets.hint}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(Object.keys(PRESETS) as PresetId[]).map((id) => (
              <button
                key={id}
                type="button"
                title={p.presets.items[id].description}
                onClick={() => setHoldings(() => PRESETS[id].map((h) => ({ ...h })))}
                className="rounded-md border border-black/20 px-3 py-1 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
              >
                {p.presets.items[id].name}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="min-w-0" aria-describedby={fieldErrors.holdings ? fieldErrorId("holdings") : undefined}>
          <legend className="text-sm font-medium">{p.holdings.heading}</legend>
          <p className="mt-1 text-xs text-black/50 dark:text-white/50">{p.holdings.hint}</p>
          <div aria-hidden className="mt-2 grid grid-cols-[minmax(0,1fr)_6rem_2rem] gap-2 text-xs text-black/60 dark:text-white/60">
            <span>{p.holdings.ticker}</span>
            <span>
              {p.holdings.weight} {p.holdings.weightUnit}
            </span>
          </div>
          <ol className="mt-1 space-y-2">
            {form.holdings.map((h, i) => {
              const n = i + 1;
              const tickerName = `holdings.${i}.ticker`;
              const weightName = `holdings.${i}.weight`;
              const tickerError = fieldErrors[tickerName];
              const weightError = fieldErrors[weightName];
              return (
                <li key={i} className="min-w-0">
                  <div className="grid grid-cols-[minmax(0,1fr)_6rem_2rem] items-center gap-2">
                    <input
                      name={tickerName}
                      aria-label={`${p.holdings.ticker} ${n}`}
                      autoCapitalize="characters"
                      spellCheck={false}
                      value={h.ticker}
                      onChange={(e) => setHolding(i, "ticker")(e.target.value)}
                      aria-invalid={tickerError ? true : undefined}
                      aria-describedby={tickerError ? fieldErrorId(tickerName) : undefined}
                      className={inputClass(tickerError)}
                    />
                    <input
                      name={weightName}
                      aria-label={`${p.holdings.weight} ${n} ${p.holdings.weightUnit}`}
                      inputMode="decimal"
                      value={h.weight}
                      onChange={(e) => setHolding(i, "weight")(e.target.value)}
                      aria-invalid={weightError ? true : undefined}
                      aria-describedby={weightError ? fieldErrorId(weightName) : undefined}
                      className={inputClass(weightError)}
                    />
                    <button
                      type="button"
                      aria-label={`${p.holdings.remove} ${n}`}
                      disabled={form.holdings.length === 1}
                      onClick={() => setHoldings((hs) => hs.filter((_, j) => j !== i))}
                      className="rounded-md px-2 py-1 text-lg leading-none text-black/60 hover:bg-black/5 disabled:opacity-30 dark:text-white/60 dark:hover:bg-white/10"
                    >
                      ×
                    </button>
                  </div>
                  <FieldError name={tickerName} message={tickerError} />
                  <FieldError name={weightName} message={weightError} />
                </li>
              );
            })}
          </ol>
          <div className="mt-2 flex items-center justify-between gap-2 text-sm">
            <button
              type="button"
              onClick={() => setHoldings((hs) => [...hs, { ticker: "", weight: "" }])}
              className="rounded-md border border-black/20 px-3 py-1 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
            >
              {p.holdings.add}
            </button>
            <span data-testid="weight-total">
              {p.holdings.total}: <span className="font-mono">{weightTotal(form.holdings)}</span>
            </span>
          </div>
          <FieldError name="holdings" message={fieldErrors.holdings} />
        </fieldset>

        <TextField
          name="benchmark"
          label={p.inputs.benchmark.label}
          hint={p.inputs.benchmark.hint}
          value={form.benchmark}
          onChange={set("benchmark")}
          error={fieldErrors.benchmark}
        />
        <div className="grid grid-cols-2 gap-4">
          <TextField
            type="date"
            name="start"
            label={p.inputs.start.label}
            hint={p.inputs.start.hint}
            value={form.start}
            onChange={set("start")}
            error={fieldErrors.start}
          />
          <TextField
            type="date"
            name="end"
            label={p.inputs.end.label}
            hint={p.inputs.end.hint}
            value={form.end}
            onChange={set("end")}
            error={fieldErrors.end}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <NumberField
            name="confidence"
            label={p.inputs.confidence.label}
            hint={p.inputs.confidence.hint}
            value={form.confidence}
            onChange={set("confidence")}
            error={fieldErrors.confidence}
          />
          <NumberField
            name="risk_free_rate"
            label={p.inputs.risk_free_rate.label}
            hint={p.inputs.risk_free_rate.hint}
            value={form.risk_free_rate}
            onChange={set("risk_free_rate")}
            error={fieldErrors.risk_free_rate}
          />
        </div>
        <button
          type="submit"
          className="w-full rounded-md bg-black px-4 py-2 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80"
        >
          {p.submit}
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
        <PortfolioResults result={result} aiTool="portfolio" />
      </section>
      <div className="min-w-0 lg:col-span-2">
        <PortfolioConstruction portfolio={request} />
      </div>
    </div>
  );
}
