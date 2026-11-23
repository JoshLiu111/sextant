"use client";

import { useState } from "react";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope } from "@/lib/envelope";
import { formatChartPercentValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { COUNTRIES, MAX_COUNTRIES, type CountryCode } from "./countries";
import { MetaList } from "./MetaList";

// Envelope ids from POST /macro/countries: metric "latest:<indicator>:<ISO3>"
// (details: year, country_name, series metadata), series "history:<indicator>:<ISO3>" (x = year).
const INDICATORS = ["gdp_growth", "inflation", "unemployment_rate"] as const;
type IndicatorKey = (typeof INDICATORS)[number];
type MetricId = `latest:${IndicatorKey}:${CountryCode}`;
type SeriesId = `history:${IndicatorKey}:${CountryCode}`;

// One color per selection slot (up to 6).
const COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2"];

function syncUrl(countries: CountryCode[]) {
  const url = new URL(window.location.href);
  url.searchParams.set("countries", countries.join(","));
  window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString().replace(/%2C/g, ",")}`);
}

export function CrossCountry({ initialCountries }: { initialCountries: CountryCode[] }) {
  const t = getMessages();
  const c = t.macro.countries;
  const [countries, setCountries] = useState<CountryCode[]>(initialCountries);
  const { result, error } = useCompute<MetricId, SeriesId>("/macro/countries", { countries });

  function toggle(code: CountryCode, on: boolean) {
    const next = on ? [...countries, code] : countries.filter((x) => x !== code);
    if (next.length === 0 || next.length > MAX_COUNTRIES) return;
    setCountries(next);
    syncUrl(next);
  }

  return (
    <section data-testid="countries" aria-labelledby="macro-countries" className="mt-10 space-y-6">
      <div>
        <h2 id="macro-countries" className="text-lg font-semibold">
          {t.macro.sections.countries}
        </h2>
        <p className="mt-1 text-sm text-black/70 dark:text-white/70">{c.intro}</p>
      </div>
      <fieldset>
        <legend className="text-sm font-medium">
          {c.picker} <span className="font-normal text-black/60 dark:text-white/60">({c.pickerHint})</span>
        </legend>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
          {COUNTRIES.map((code) => {
            const checked = countries.includes(code);
            const disabled = checked ? countries.length === 1 : countries.length >= MAX_COUNTRIES;
            return (
              <label key={code} className={`flex items-center gap-1.5 text-sm ${disabled ? "opacity-50" : ""}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={(e) => toggle(code, e.target.checked)}
                />
                {c.names[code]}
              </label>
            );
          })}
        </div>
      </fieldset>
      {error && <ErrorNotice title={t.common.errors.heading} message={error} />}
      <div className="grid gap-6 lg:grid-cols-2">
        {INDICATORS.map((key) => (
          <CountryIndicator key={key} id={key} countries={countries} result={result} />
        ))}
      </div>
      {result && <CalculationInfo result={result} />}
    </section>
  );
}

function CountryIndicator({
  id,
  countries,
  result,
}: {
  id: IndicatorKey;
  countries: CountryCode[];
  result: ResultEnvelope<MetricId, SeriesId> | null;
}) {
  const t = getMessages();
  const c = t.macro.countries;
  const explainer = c.indicators[id];
  const latest = (code: CountryCode) => result?.metrics[`latest:${id}:${code}`];
  const series: ChartSeries[] = countries.flatMap((code, i) => {
    const s = result?.series[`history:${id}:${code}`];
    if (!s || s.status !== "ok") return [];
    return [
      { id: code, label: c.names[code], points: s.points.map((p) => ({ x: Number(p.x), y: p.y })), color: COLORS[i] },
    ];
  });
  const meta = countries.map(latest).find((m) => m?.status === "ok");

  return (
    <article data-indicator={`country:${id}`} className="min-w-0 space-y-3">
      <MetricCard
        id={`country:${id}`}
        explainer={explainer}
        values={countries.map((code) => {
          const r = latest(code);
          return {
            id: `latest:${id}:${code}`,
            label: c.names[code],
            result: r,
            note: r?.status === "ok" ? String(r.details.year ?? "") : undefined,
          };
        })}
      />
      {meta && <WorldBankMeta details={meta.details} />}
      {series.length > 0 && (
        <LineChart
          label={`${explainer.name} ${c.chartSuffix}`}
          series={series}
          xLabel={c.x}
          formatX={(x) => String(x)}
          formatY={formatChartPercentValue}
          height={240}
        />
      )}
    </article>
  );
}

function WorldBankMeta({ details }: { details: MetricResult["details"] }) {
  const t = getMessages().macro;
  const text = (key: string) => String(details[key] ?? "");
  const indicator = text("indicator_id");

  return (
    <MetaList
      rows={[
        {
          label: t.meta.source,
          value: (
            <>
              {t.countries.dataset},{" "}
              <a
                href={`https://data.worldbank.org/indicator/${encodeURIComponent(indicator)}`}
                className="font-mono underline"
                target="_blank"
                rel="noreferrer"
              >
                {indicator}
              </a>
            </>
          ),
        },
        { label: t.countries.originalSource, value: text("source") },
        { label: t.meta.units, value: text("units") },
        { label: t.meta.frequency, value: text("frequency") },
        // WDI publishes a date only, no time.
        { label: t.meta.lastUpdated, value: text("last_updated") },
      ]}
    />
  );
}
