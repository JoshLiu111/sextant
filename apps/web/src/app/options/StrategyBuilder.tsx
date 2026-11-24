"use client";

import { useState, type FormEvent } from "react";
import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import { formatChartNumber } from "@/lib/format";
import { decodeRows, encodeRows, fieldsCodec, useUrlInputs, type UrlCodec } from "@/lib/urlInputs";
import { useCompute } from "@/lib/useCompute";
import { STICKY_INPUTS, toolColumns } from "@/lib/layout";
import { chartPoints, MARKET_DEFAULTS, MARKET_FIELDS, marketRequest, toNumber, type MarketForm } from "./form";
import {
  DEFAULT_PRESET,
  PRESET_IDS,
  presetLegs,
  type Instrument,
  type LegForm,
  type Position,
} from "./strategyPresets";
import { series } from "@/lib/chartColors";

const GREEKS = ["delta", "gamma", "vega", "theta", "rho"] as const;
type Greek = (typeof GREEKS)[number];
type Axis = "spot" | "time";

type MetricId = "net_cost" | "max_profit" | "max_loss" | Greek;
type SeriesId = "profit_at_expiry" | "profit_today" | `${Greek}_vs_spot` | `${Greek}_vs_time`;

const INSTRUMENTS: Instrument[] = ["call", "put", "underlying"];
const POSITIONS: Position[] = ["long", "short"];

type StrategyForm = { market: MarketForm; legs: LegForm[] };

function defaultLegs(spot: string): LegForm[] {
  const n = Number(spot);
  return presetLegs(DEFAULT_PRESET, Number.isFinite(n) && n > 0 ? n : Number(MARKET_DEFAULTS.spot));
}

// Shareable links: the market fields one param each, plus
// `legs=call:long:1:100,call:short:1:110` (instrument:position:quantity:strike).
// Without `legs` the default preset is built around the linked spot.
const MARKET_CODEC = fieldsCodec(MARKET_DEFAULTS);
const URL_CODEC: UrlCodec<StrategyForm> = {
  keys: [...MARKET_CODEC.keys, "legs"],
  read(params) {
    const market = MARKET_CODEC.read(params);
    const raw = params.get("legs");
    const legs =
      raw === null
        ? defaultLegs(market.spot)
        : decodeRows(raw, 4).map(([instrument, position, quantity, strike]) => ({
            instrument: instrument as Instrument,
            position: position as Position,
            quantity,
            strike,
          }));
    return { market, legs };
  },
  write: ({ market, legs }) => ({
    ...MARKET_CODEC.write(market),
    legs: encodeRows(legs.map((leg) => [leg.instrument, leg.position, leg.quantity, leg.strike])),
  }),
};

function toRequest(market: MarketForm, legs: LegForm[]) {
  return {
    ...marketRequest(market),
    legs: legs.map((leg) => ({
      instrument: leg.instrument,
      position: leg.position,
      quantity: toNumber(leg.quantity),
      strike: leg.instrument === "underlying" ? null : toNumber(leg.strike),
    })),
  };
}

// `.field` draws the error border from aria-invalid; the class only adds it for the first paint.
const inputClass = (error: string | undefined) => `field mt-1 text-sm text-ink ${error ? "border-error" : ""}`;
const selectClass = "field mt-1 text-sm text-ink";

export function StrategyBuilder() {
  const t = getMessages();
  const o = t.options;
  const s = o.strategy;
  const { initial, share } = useUrlInputs(URL_CODEC);
  const [market, setMarket] = useState<MarketForm>(initial.market);
  const [legs, setLegs] = useState<LegForm[]>(initial.legs);
  const [greek, setGreek] = useState<Greek>("delta");
  const [axis, setAxis] = useState<Axis>("spot");
  const { result, fieldErrors, error, run } = useCompute<MetricId, SeriesId>("/options/strategy", toRequest(market, legs));
  const m = result?.metrics;

  const setLeg = (i: number, field: keyof LegForm) => (value: string) =>
    setLegs((ls) => ls.map((leg, j) => (j === i ? { ...leg, [field]: value } : leg)));

  function loadPreset(id: (typeof PRESET_IDS)[number]) {
    const spot = Number(market.spot);
    setLegs(presetLegs(id, Number.isFinite(spot) && spot > 0 ? spot : Number(MARKET_DEFAULTS.spot)));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    share({ market, legs });
    run();
  }

  const resultSpot = Number(result?.meta.parameters.spot);
  const resultTime = Number(result?.meta.parameters.time_to_expiry);
  const profitSeries: ChartSeries[] = result
    ? [
        { id: "profit_at_expiry", label: s.chart.atExpiry, points: chartPoints(result.series.profit_at_expiry), color: series(0) },
        {
          id: "profit_today",
          label: s.chart.today,
          points: chartPoints(result.series.profit_today),
          color: series(1),
          dashed: true,
        },
      ]
    : [];
  const greekSeries: ChartSeries[] = result
    ? [
        {
          id: `${greek}_vs_${axis}`,
          label: s.metrics[greek].name,
          points: chartPoints(result.series[`${greek}_vs_${axis}`]),
          color: series(2),
        },
      ]
    : [];

  return (
    <div className={`mt-6 ${toolColumns("22rem")}`}>
      <form onSubmit={onSubmit} noValidate aria-labelledby="strategy-inputs" className={`${STICKY_INPUTS} space-y-6`}>
        <p className="max-w-[55ch] text-sm text-ink-2">{s.intro}</p>
        <fieldset className="min-w-0">
          <legend className="label">{s.presets.heading}</legend>
          <p className="hint mt-1">{s.presets.hint}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {PRESET_IDS.map((id) => (
              <button
                key={id}
                type="button"
                title={s.presets.items[id].description}
                onClick={() => loadPreset(id)}
                className="btn btn-sm"
              >
                {s.presets.items[id].name}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="min-w-0" aria-describedby={fieldErrors.legs ? fieldErrorId("legs") : undefined}>
          <legend className="label">{s.legs.heading}</legend>
          <ol className="mt-2 space-y-3 border-t border-rule pt-3">
            {legs.map((leg, i) => {
              const n = i + 1;
              const name = (field: string) => `legs.${i}.${field}`;
              const quantityError = fieldErrors[name("quantity")];
              const strikeError = fieldErrors[name("strike")];
              return (
                <li
                  key={i}
                  data-testid="strategy-leg"
                  className="min-w-0 border-b border-rule pb-3"
                >
                  <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-end gap-2">
                    <label className="min-w-0 text-xs text-muted">
                      {s.legs.instrument}
                      <select
                        name={name("instrument")}
                        aria-label={`${s.legs.instrument} ${n}`}
                        value={leg.instrument}
                        onChange={(e) => setLeg(i, "instrument")(e.target.value)}
                        className={selectClass}
                      >
                        {INSTRUMENTS.map((v) => (
                          <option key={v} value={v}>
                            {s.legs.instruments[v]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="min-w-0 text-xs text-muted">
                      {s.legs.position}
                      <select
                        name={name("position")}
                        aria-label={`${s.legs.position} ${n}`}
                        value={leg.position}
                        onChange={(e) => setLeg(i, "position")(e.target.value)}
                        className={selectClass}
                      >
                        {POSITIONS.map((v) => (
                          <option key={v} value={v}>
                            {s.legs.positions[v]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      aria-label={`${s.legs.remove} ${n}`}
                      disabled={legs.length === 1}
                      onClick={() => setLegs((ls) => ls.filter((_, j) => j !== i))}
                      className="btn btn-sm w-8 px-0 text-lg leading-none"
                    >
                      ×
                    </button>
                  </div>
                  <div className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] gap-2">
                    <label className="min-w-0 text-xs text-muted">
                      {s.legs.quantity}
                      <input
                        name={name("quantity")}
                        aria-label={`${s.legs.quantity} ${n}`}
                        type="number"
                        inputMode="decimal"
                        step="any"
                        value={leg.quantity}
                        onChange={(e) => setLeg(i, "quantity")(e.target.value)}
                        aria-invalid={quantityError ? true : undefined}
                        aria-describedby={quantityError ? fieldErrorId(name("quantity")) : undefined}
                        className={inputClass(quantityError)}
                      />
                    </label>
                    <label className="min-w-0 text-xs text-muted">
                      {s.legs.strike}
                      <input
                        name={name("strike")}
                        aria-label={`${s.legs.strike} ${n}`}
                        type="number"
                        inputMode="decimal"
                        step="any"
                        disabled={leg.instrument === "underlying"}
                        value={leg.instrument === "underlying" ? "" : leg.strike}
                        onChange={(e) => setLeg(i, "strike")(e.target.value)}
                        aria-invalid={strikeError ? true : undefined}
                        aria-describedby={strikeError ? fieldErrorId(name("strike")) : undefined}
                        className={inputClass(strikeError)}
                      />
                    </label>
                  </div>
                  <FieldError name={name("quantity")} message={quantityError} />
                  <FieldError name={name("strike")} message={strikeError} />
                </li>
              );
            })}
          </ol>
          <button
            type="button"
            onClick={() =>
              setLegs((ls) => [...ls, { instrument: "call", position: "long", quantity: "1", strike: market.spot }])
            }
            className="btn btn-sm mt-2"
          >
            {s.legs.add}
          </button>
          <FieldError name="legs" message={fieldErrors.legs} />
        </fieldset>

        <fieldset className="min-w-0">
          <legend id="strategy-inputs" className="label">
            {s.marketHeading}
          </legend>
          <div className="mt-2 grid grid-cols-2 gap-4">
            {MARKET_FIELDS.map((field) => (
              <NumberField
                key={field}
                name={field}
                label={o.inputs[field].label}
                hint={o.inputs[field].hint}
                value={market[field]}
                onChange={(v) => setMarket((f) => ({ ...f, [field]: v }))}
                error={fieldErrors[field]}
              />
            ))}
          </div>
        </fieldset>
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
          <h2 className="text-xl">{s.sections.summary}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-3">
            {(["net_cost", "max_profit", "max_loss"] as const).map((id) => (
              <MetricCard key={id} id={id} explainer={s.metrics[id]} values={[{ id, result: m?.[id] }]} />
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-xl">{s.sections.greeks}</h2>
          <div className="mt-2 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {GREEKS.map((id) => (
              <MetricCard key={id} id={id} explainer={s.metrics[id]} values={[{ id, result: m?.[id] }]} />
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-xl">{s.sections.payoff}</h2>
          <div className="mt-2">
            {result && (
              <LineChart
                label={s.chart.label}
                series={profitSeries}
                xLabel={s.chart.x}
                formatX={formatChartNumber}
                formatY={formatChartNumber}
                markers={[{ x: resultSpot, label: s.chart.spot }]}
              />
            )}
          </div>
        </div>
        <div>
          <h2 className="text-xl">{s.sections.curves}</h2>
          <div className="mt-2 flex flex-wrap gap-4">
            <div className="text-sm text-muted">
              <label htmlFor="strategy-greek">{s.curves.greek}</label>
              <select
                id="strategy-greek"
                value={greek}
                onChange={(e) => setGreek(e.target.value as Greek)}
                className={`${selectClass} w-auto`}
              >
                {GREEKS.map((g) => (
                  <option key={g} value={g}>
                    {s.metrics[g].name}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-sm text-muted">
              <label htmlFor="strategy-axis">{s.curves.against}</label>
              <select
                id="strategy-axis"
                value={axis}
                onChange={(e) => setAxis(e.target.value as Axis)}
                className={`${selectClass} w-auto`}
              >
                <option value="spot">{s.curves.spot}</option>
                <option value="time">{s.curves.time}</option>
              </select>
            </div>
          </div>
          <div className="mt-2">
            {result && (
              <LineChart
                label={`${s.curves.label}: ${s.metrics[greek].name}`}
                series={greekSeries}
                xLabel={axis === "spot" ? s.curves.spot : s.curves.time}
                formatX={formatChartNumber}
                formatY={(y) => y.toFixed(4)}
                markers={[{ x: axis === "spot" ? resultSpot : resultTime, label: s.curves.now }]}
              />
            )}
          </div>
        </div>
        {result && <CalculationInfo result={result} />}
        {result && <AiExplain tool="options-strategy" result={result} />}
      </section>
    </div>
  );
}
