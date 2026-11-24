"use client";

import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { LineChart } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import { csvFilename } from "@/lib/csv";
import type { MetricResult, ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartPercentValue, formatTimestampUtc } from "@/lib/format";
import { series } from "@/lib/chartColors";

// Envelope ids: metric "latest:<key>" (details carry the series metadata), series "history:<key>".
const INDICATORS = ["gdp_growth", "cpi_inflation", "unemployment_rate", "fed_funds_rate"] as const;
type IndicatorKey = (typeof INDICATORS)[number];
export type IndicatorMetricId = `latest:${IndicatorKey}`;
export type IndicatorSeriesId = `history:${IndicatorKey}`;

const COLORS: Record<IndicatorKey, string> = {
  gdp_growth: series(0),
  cpi_inflation: series(1),
  unemployment_rate: series(2),
  fed_funds_rate: series(3),
};

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/** POST /macro/indicators results; `MacroTool` owns the request (the chart range). */
export function MacroDashboard({
  result,
  error,
}: {
  result: ResultEnvelope<IndicatorMetricId, IndicatorSeriesId> | null;
  error: string | null;
}) {
  const t = getMessages();

  return (
    <section data-testid="results" aria-labelledby="macro-indicators" className="mt-6 space-y-6">
      <h3 id="macro-indicators" className="text-xl">
        {t.macro.sections.indicators}
      </h3>
      {error && <ErrorNotice title={t.common.errors.heading} message={error} />}
      <div className="grid gap-6 lg:grid-cols-2">
        {INDICATORS.map((key) => (
          <Indicator
            key={key}
            id={key}
            latest={result?.metrics[`latest:${key}`]}
            history={result?.series[`history:${key}`]}
          />
        ))}
      </div>
      {result && <CalculationInfo result={result} />}
      {result && <AiExplain tool="macro" result={result} />}
    </section>
  );
}

function Indicator({
  id,
  latest,
  history,
}: {
  id: IndicatorKey;
  latest: MetricResult | undefined;
  history: SeriesResult | undefined;
}) {
  const t = getMessages();
  const explainer = t.macro.indicators[id];
  const points = chartPoints(history);

  return (
    <article data-indicator={id} className="min-w-0 space-y-3">
      <MetricCard id={id} explainer={explainer} values={[{ id: `latest:${id}`, result: latest }]} />
      {latest?.status === "ok" && <SeriesMeta details={latest.details} />}
      {history?.status === "ok" && history.points.length > 0 && (
        <div className="flex justify-end">
          <ExportCsvButton
            label={`${explainer.name} ${t.macro.chart.history}`}
            filename={csvFilename("macro", id, String(latest?.details.series_id ?? ""))}
            table={{
              columns: [t.macro.chart.x, `${explainer.name} (${String(latest?.details.units ?? "")})`],
              rows: history.points.map((p) => [String(p.x), p.y]),
            }}
          />
        </div>
      )}
      {points.length > 0 && (
        <LineChart
          label={`${explainer.name} ${t.macro.chart.history}`}
          series={[{ id, label: explainer.name, points, color: COLORS[id] }]}
          xLabel={t.macro.chart.x}
          formatX={formatChartDate}
          formatY={formatChartPercentValue}
          height={220}
        />
      )}
    </article>
  );
}

export function SeriesMeta({ details }: { details: MetricResult["details"] }) {
  const m = getMessages().macro.meta;
  const text = (key: string) => String(details[key] ?? "");
  const seriesId = text("series_id");

  return (
    <dl
      data-testid="series-meta"
      className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm text-ink-2"
    >
      <dt className="text-muted">{m.source}</dt>
      <dd>
        {text("source")}, {m.via}{" "}
        <a
          href={`https://fred.stlouisfed.org/series/${encodeURIComponent(seriesId)}`}
          className="link tabular-nums"
          target="_blank"
          rel="noreferrer"
        >
          {seriesId}
        </a>
      </dd>
      <dt className="text-muted">{m.units}</dt>
      <dd>{text("units")}</dd>
      <dt className="text-muted">{m.frequency}</dt>
      <dd>
        {text("frequency")} ({text("seasonal_adjustment")})
      </dd>
      <dt className="text-muted">{m.latestPeriod}</dt>
      <dd>{text("date")}</dd>
      <dt className="text-muted">{m.lastUpdated}</dt>
      <dd>{formatTimestampUtc(text("last_updated"))}</dd>
    </dl>
  );
}
