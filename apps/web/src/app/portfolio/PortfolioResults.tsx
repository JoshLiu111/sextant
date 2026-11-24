"use client";

import { AiExplain } from "@/components/AiExplain";
import { CalculationInfo } from "@/components/CalculationInfo";
import { ExportCsvButton } from "@/components/ExportCsvButton";
import { KeyFiguresStrip } from "@/components/KeyFiguresStrip";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { getMessages } from "@/i18n";
import type { ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { csvFilename } from "@/lib/csv";
import { formatChartDate, formatChartPercent } from "@/lib/format";

/** The P3 metric set, scored for the portfolio and the benchmark. Explainers are shared with Risk & Performance. */
const METRICS = [
  "annualized_return",
  "annualized_volatility",
  "max_drawdown",
  "var",
  "cvar",
  "sharpe",
  "sortino",
  "beta",
] as const;

/** The headline figures of the overview, picked from METRICS (the portfolio's, not the benchmark's). */
const KEY_FIGURES = ["annualized_return", "annualized_volatility", "max_drawdown", "sharpe"] as const;

/** Envelope ids: metrics `<metric>:<who>`, series `cumulative_return:<who>`. */
const WHO = ["portfolio", "benchmark"] as const;

export type PortfolioEnvelope = ResultEnvelope<string, string>;

type AiTool = "portfolio" | "portfolio-saved";

/** File-name input for a portfolio export: the saved name, else the holdings' tickers. */
export function portfolioCsvInput(result: PortfolioEnvelope): string {
  const params = result.meta.parameters as { name?: string; holdings?: { ticker: string }[] };
  return params.name ?? (params.holdings ?? []).map((h) => h.ticker).join("_");
}

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/**
 * The performance and risk view of one portfolio result from `POST /portfolio/metrics` or `POST /portfolios/{id}/metrics`:
 * the overview, then the calculation info and AI Explain. Used by saved portfolios;
 * the demo portfolio puts the two parts around its tabs. `metricsNote` says how the return series was built.
 */
export function PortfolioResults({
  result,
  metricsNote,
  aiTool,
}: {
  result: PortfolioEnvelope | null;
  metricsNote?: string;
  /** The AI Explain endpoint for this result: `portfolio` (demo) or `portfolio-saved`. */
  aiTool: AiTool;
}) {
  return (
    <>
      <PortfolioOverview result={result} metricsNote={metricsNote} />
      <PortfolioResultDetails result={result} aiTool={aiTool} />
    </>
  );
}

/**
 * Cumulative return vs the benchmark and the risk metric cards, optionally led by
 * a strip of the portfolio's headline figures.
 */
export function PortfolioOverview({
  result,
  metricsNote,
  keyFigures = false,
}: {
  result: PortfolioEnvelope | null;
  metricsNote?: string;
  keyFigures?: boolean;
}) {
  const t = getMessages();
  const p = t.portfolio;
  const benchmark = (result?.meta.parameters as { benchmark?: string } | undefined)?.benchmark ?? "";
  const labels = { portfolio: p.portfolioLabel, benchmark: `${benchmark} ${p.benchmarkSuffix}` };
  const chartSeries: ChartSeries[] = result
    ? [
        {
          id: "portfolio",
          label: labels.portfolio,
          points: chartPoints(result.series["cumulative_return:portfolio"]),
          color: "#2563eb",
        },
        {
          id: "benchmark",
          label: labels.benchmark,
          points: chartPoints(result.series["cumulative_return:benchmark"]),
          color: "#64748b",
          dashed: true,
        },
      ]
    : [];

  return (
    <div className="space-y-6">
      {keyFigures && (
        <KeyFiguresStrip
          figures={KEY_FIGURES.map((id) => ({
            id: `${id}:portfolio`,
            label: t.risk.metrics[id].name,
            sublabel: labels.portfolio,
            result: result?.metrics[`${id}:portfolio`],
          }))}
        />
      )}
      <div>
        <h2 className="text-lg font-semibold">{p.sections.chart}</h2>
        <div className="mt-2">
          {result && (
            <LineChart
              label={p.chart.label}
              series={chartSeries}
              xLabel={p.chart.x}
              formatX={formatChartDate}
              formatY={formatChartPercent}
            />
          )}
        </div>
      </div>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{p.sections.metrics}</h2>
          {result && (
            <ExportCsvButton
              label={p.sections.metrics}
              filename={csvFilename("portfolio", "risk", portfolioCsvInput(result))}
              demo={result.source.is_demo}
              table={{
                columns: [t.common.csv.metric, labels.portfolio, labels.benchmark],
                rows: METRICS.map((id) => [
                  t.risk.metrics[id].name,
                  ...WHO.map((who) => result.metrics[`${id}:${who}`]),
                ]),
              }}
            />
          )}
        </div>
        <p className="mt-1 text-sm text-black/70 dark:text-white/70">{metricsNote ?? p.sections.metricsNote}</p>
        <div className="mt-2 grid gap-4 xl:grid-cols-3">
          {METRICS.map((id) => (
            <MetricCard
              key={id}
              id={id}
              explainer={t.risk.metrics[id]}
              values={WHO.map((who) => ({
                id: `${id}:${who}`,
                label: result ? labels[who] : undefined,
                result: result?.metrics[`${id}:${who}`],
              }))}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Calculation info and AI Explain for one portfolio result. */
export function PortfolioResultDetails({ result, aiTool }: { result: PortfolioEnvelope | null; aiTool: AiTool }) {
  if (!result) return null;
  return (
    <>
      <CalculationInfo result={result} />
      <AiExplain tool={aiTool} result={result} />
    </>
  );
}
