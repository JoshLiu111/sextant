"use client";

import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { LineChart, type ChartBand, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { MetricResult, ResultEnvelope, SeriesResult } from "@/lib/envelope";
import {
  formatChartDate,
  formatChartMaturity,
  formatChartPercentPoints,
  formatTimestampUtc,
  formatValue,
} from "@/lib/format";
import { REFERENCE, series } from "@/lib/chartColors";

// Envelope ids from POST /macro/rates. Curves: x = maturity in years, details.date
// = the curve's date. The spread history's bands are its inversion periods.
const CURVES = [
  { key: "latest", color: series(0), dashed: false },
  { key: "1m_ago", color: series(1), dashed: true },
  { key: "1y_ago", color: REFERENCE, dashed: true },
] as const;
type CurveKey = (typeof CURVES)[number]["key"];
export type RatesMetricId = "latest:yield_2y" | "latest:yield_10y" | "latest:spread_10y_2y";
export type RatesSeriesId = `yield_curve:${CurveKey}` | "history:spread_10y_2y";

const TREASURY_PAGE =
  "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve";

/** POST /macro/rates results; `MacroTool` owns the request (the chart range). */
export function TreasuryRates({
  result,
  error,
}: {
  result: ResultEnvelope<RatesMetricId, RatesSeriesId> | null;
  error: string | null;
}) {
  const t = getMessages();

  return (
    <section data-testid="rates" aria-labelledby="macro-rates" className="mt-10 space-y-6">
      <h3 id="macro-rates" className="text-xl">
        {t.macro.sections.rates}
      </h3>
      {error && <ErrorNotice title={t.common.errors.heading} message={error} />}
      <div className="grid gap-6 lg:grid-cols-2">
        <YieldCurve
          yields={[result?.metrics["latest:yield_2y"], result?.metrics["latest:yield_10y"]]}
          curves={CURVES.map((c) => result?.series[`yield_curve:${c.key}`])}
        />
        <TermSpread latest={result?.metrics["latest:spread_10y_2y"]} history={result?.series["history:spread_10y_2y"]} />
      </div>
      {result && <CalculationInfo result={result} />}
      {result && <AiExplain tool="macro-rates" result={result} />}
    </section>
  );
}

function YieldCurve({
  yields: [twoYear, tenYear],
  curves,
}: {
  yields: (MetricResult | undefined)[];
  curves: (SeriesResult | undefined)[];
}) {
  const t = getMessages();
  const r = t.macro.rates;
  const series: ChartSeries[] = CURVES.flatMap((c, i) => {
    const s = curves[i];
    if (!s || s.status !== "ok") return [];
    return [
      {
        id: c.key,
        label: `${r.curveLabels[c.key]} (${String(s.details.date ?? "")})`,
        points: s.points.map((p) => ({ x: Number(p.x), y: p.y })),
        color: c.color,
        dashed: c.dashed,
      },
    ];
  });

  return (
    <article data-indicator="yield_curve" className="min-w-0 space-y-3">
      <MetricCard
        id="yield_curve"
        explainer={r.yield_curve}
        values={[
          { id: "latest:yield_2y", label: r.yieldLabels.yield_2y, result: twoYear },
          { id: "latest:yield_10y", label: r.yieldLabels.yield_10y, result: tenYear },
        ]}
      />
      {tenYear?.status === "ok" && <TreasuryMeta details={tenYear.details} />}
      {series.length > 0 && <YieldCurveExport curves={curves} />}
      {series.length > 0 && (
        <LineChart
          label={r.curveChart}
          series={series}
          xLabel={t.macro.chart.maturity}
          formatX={formatChartMaturity}
          // Two decimals, as Treasury publishes them ("4.63%").
          formatY={(y) => formatValue(y, "percent")}
          height={260}
        />
      )}
    </article>
  );
}

/** One row per maturity (years), one column per curve, yields in percent. */
function YieldCurveExport({ curves }: { curves: (SeriesResult | undefined)[] }) {
  const t = getMessages();
  const r = t.macro.rates;
  const shown = CURVES.flatMap((c, i) => {
    const s = curves[i];
    return s && s.status === "ok" ? [{ key: c.key, series: s }] : [];
  });
  const maturities = [...new Set(shown.flatMap((c) => c.series.points.map((p) => Number(p.x))))].sort((a, b) => a - b);
  const byMaturity = shown.map((c) => new Map(c.series.points.map((p) => [Number(p.x), p.y])));
  const latestDate = String(shown[0]?.series.details.date ?? "");
  return (
    <div className="flex justify-end">
      <ExportCsvButton
        label={r.curveChart}
        filename={csvFilename("macro", "yield-curve", latestDate)}
        table={{
          columns: [
            t.macro.chart.maturityYears,
            ...shown.map((c) => `${r.curveLabels[c.key]} (${String(c.series.details.date ?? "")}) (%)`),
          ],
          rows: maturities.map((m) => [m, ...byMaturity.map((values) => values.get(m) ?? null)]),
        }}
      />
    </div>
  );
}

function TermSpread({ latest, history }: { latest: MetricResult | undefined; history: SeriesResult | undefined }) {
  const t = getMessages();
  const r = t.macro.rates;
  const ok = history?.status === "ok" ? history : undefined;
  const points = ok ? ok.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y })) : [];
  const bands: ChartBand[] = ok
    ? ok.bands.map((b) => ({ start: Date.parse(String(b.start)), end: Date.parse(String(b.end)), label: r.inverted }))
    : [];

  return (
    <article data-indicator="spread_10y_2y" className="min-w-0 space-y-3">
      <MetricCard id="spread_10y_2y" explainer={r.spread_10y_2y} values={[{ id: "latest:spread_10y_2y", result: latest }]} />
      {latest?.status === "ok" && <TreasuryMeta details={latest.details} />}
      {ok && ok.points.length > 0 && (
        <div className="flex justify-end">
          <ExportCsvButton
            label={r.spreadChart}
            filename={csvFilename("macro", "spread-10y-2y", String(latest?.details.date ?? ""))}
            table={{
              columns: [t.macro.chart.x, `${r.spread_10y_2y.name} (${t.common.units.percentage_points})`],
              rows: ok.points.map((p) => [String(p.x), p.y]),
            }}
          />
        </div>
      )}
      {points.length > 0 && (
        <LineChart
          label={r.spreadChart}
          series={[{ id: "spread_10y_2y", label: r.spread_10y_2y.name, points, color: series(2) }]}
          bands={bands}
          xLabel={t.macro.chart.x}
          formatX={formatChartDate}
          formatY={formatChartPercentPoints}
          height={260}
        />
      )}
    </article>
  );
}

function TreasuryMeta({ details }: { details: MetricResult["details"] }) {
  const m = getMessages().macro.meta;
  const text = (key: string) => String(details[key] ?? "");

  return (
    <dl
      data-testid="series-meta"
      className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm text-ink-2"
    >
      <dt className="font-medium">{m.source}</dt>
      <dd>
        {text("source")},{" "}
        <a href={TREASURY_PAGE} className="underline" target="_blank" rel="noreferrer">
          {text("title")}
        </a>
      </dd>
      <dt className="font-medium">{m.units}</dt>
      <dd>{text("units")}</dd>
      <dt className="font-medium">{m.frequency}</dt>
      <dd>{text("frequency")}</dd>
      <dt className="font-medium">{m.latestPeriod}</dt>
      <dd>{text("date")}</dd>
      <dt className="font-medium">{m.lastUpdated}</dt>
      <dd>
        {formatTimestampUtc(text("last_updated"))} ({m.retrieved})
      </dd>
    </dl>
  );
}
