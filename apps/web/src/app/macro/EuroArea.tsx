"use client";

import { CalculationInfo } from "@/components/CalculationInfo";
import { ErrorNotice } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import type { MetricResult, SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartPercentValue, formatTimestampUtc, formatValue } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { MetaList } from "./MetaList";
import { series } from "@/lib/chartColors";

// Envelope ids from POST /macro/euro-area. Rates: details.date = when the rate took
// effect, history drawn as a step line. HICP: details.date = the month (YYYY-MM).
const RATES = [
  { key: "deposit_facility_rate", color: series(0) },
  { key: "main_refinancing_rate", color: series(1) },
  { key: "marginal_lending_rate", color: series(2) },
] as const;
type RateKey = (typeof RATES)[number]["key"];
type Key = RateKey | "hicp_inflation";
type MetricId = `latest:${Key}`;
type SeriesId = `history:${Key}`;

const DATA_PORTAL = "https://data.ecb.europa.eu/data/datasets";

// No inputs yet: the endpoint's defaults pick the range (2015 to today).
const REQUEST = {};

function datePoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

export function EuroArea() {
  const t = getMessages();
  const e = t.macro.euroArea;
  const { result, error } = useCompute<MetricId, SeriesId>("/macro/euro-area", REQUEST);

  const rateSeries: ChartSeries[] = RATES.flatMap((r) => {
    const points = datePoints(result?.series[`history:${r.key}`]);
    return points.length > 0 ? [{ id: r.key, label: e.rateLabels[r.key], points, color: r.color }] : [];
  });
  const hicpPoints = datePoints(result?.series["history:hicp_inflation"]);
  const dfr = result?.metrics["latest:deposit_facility_rate"];
  const hicp = result?.metrics["latest:hicp_inflation"];

  return (
    <section id="euro-area" data-testid="euro-area" aria-labelledby="macro-euro-area" className="mt-12 space-y-6 border-t border-rule pt-8">
      <div>
        <h2 id="macro-euro-area" className="text-2xl">
          {t.macro.sections.euroArea}
        </h2>
        <p className="mt-2 max-w-[75ch] text-sm text-ink-2">{e.intro}</p>
      </div>
      {error && <ErrorNotice title={t.common.errors.heading} message={error} />}
      <div className="grid gap-6 lg:grid-cols-2">
        <article data-indicator="ecb_rates" className="min-w-0 space-y-3">
          <MetricCard
            id="ecb_rates"
            explainer={e.ecb_rates}
            values={RATES.map((r) => {
              const m = result?.metrics[`latest:${r.key}`];
              return {
                id: `latest:${r.key}`,
                label: e.rateLabels[r.key],
                result: m,
                note: m?.status === "ok" ? `${e.since} ${String(m.details.date ?? "")}` : undefined,
              };
            })}
          />
          {dfr?.status === "ok" && <EcbMeta details={dfr.details} />}
          {rateSeries.length > 0 && (
            <LineChart
              label={e.ratesChart}
              series={rateSeries}
              xLabel={t.macro.chart.x}
              formatX={formatChartDate}
              // Two decimals, as the ECB sets them ("2.65%").
              formatY={(y) => formatValue(y, "percent")}
              height={260}
            />
          )}
        </article>
        <article data-indicator="hicp_inflation" className="min-w-0 space-y-3">
          <MetricCard
            id="hicp_inflation"
            explainer={e.hicp_inflation}
            values={[{ id: "latest:hicp_inflation", result: hicp }]}
          />
          {hicp?.status === "ok" && <EcbMeta details={hicp.details} />}
          {hicpPoints.length > 0 && (
            <LineChart
              label={e.hicpChart}
              series={[{ id: "hicp_inflation", label: e.hicp_inflation.name, points: hicpPoints, color: series(3) }]}
              xLabel={t.macro.chart.x}
              formatX={formatChartDate}
              formatY={formatChartPercentValue}
              height={260}
            />
          )}
        </article>
      </div>
      {result && <CalculationInfo result={result} />}
    </section>
  );
}

function EcbMeta({ details }: { details: MetricResult["details"] }) {
  const m = getMessages().macro.meta;
  const text = (key: string) => String(details[key] ?? "");
  const adjustment = text("seasonal_adjustment");
  // "FM/B.U2.EUR.4F.KR.DFR.LEV" -> the portal's series page .../FM/FM.B.U2.EUR.4F.KR.DFR.LEV
  const [flow, key] = text("series_id").split("/");
  const href = flow && key ? `${DATA_PORTAL}/${flow}/${flow}.${key}` : DATA_PORTAL;

  return (
    <MetaList
      rows={[
        {
          label: m.source,
          value: (
            <>
              {text("source")},{" "}
              <a href={href} className="link" target="_blank" rel="noreferrer">
                {text("title")}
              </a>{" "}
              (<span className="tabular-nums">{text("series_id")}</span>)
            </>
          ),
        },
        { label: m.units, value: text("units") },
        { label: m.frequency, value: adjustment ? `${text("frequency")} (${adjustment})` : text("frequency") },
        { label: m.latestPeriod, value: text("date") },
        { label: m.lastUpdated, value: formatTimestampUtc(text("last_updated")) },
      ]}
    />
  );
}
