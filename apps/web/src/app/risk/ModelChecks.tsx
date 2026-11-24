"use client";

import { useState } from "react";
import { LineChart } from "@/components/LineChart";
import { MetricExplainer } from "@/components/MetricExplainer";
import { getMessages } from "@/i18n";
import type { MetricResult, ResultEnvelope, SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartPercent, formatValue } from "@/lib/format";
import { series } from "@/lib/chartColors";

// Metric ids "<method>:<ticker>" and "garch_volatility:<ticker>"; series "garch_volatility:<ticker>".
// See apps/compute/sextant_compute/risk/model_checks.py.
const BACKTEST_METHODS = ["backtest_var", "backtest_parametric_var", "backtest_cornish_fisher_var"] as const;
const GARCH = "garch_volatility";

const ONE = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const TWO = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FOUR = new Intl.NumberFormat("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const SCIENTIFIC = new Intl.NumberFormat("en-US", { notation: "scientific", maximumFractionDigits: 3 });

function num(result: MetricResult | undefined, key: string): number | null {
  const v = result?.status === "ok" ? result.details[key] : null;
  return typeof v === "number" ? v : null;
}

function show(value: number | null, format: (n: number) => string): string {
  return value === null ? "–" : format(value);
}

function pValue(p: number): string {
  return p < 0.0001 ? "< 0.0001" : FOUR.format(p);
}

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/**
 * VaR backtests (Kupiec) and GARCH(1,1) volatility for one ticker at a time,
 * from the Risk & Performance envelope.
 */
export function ModelChecks({
  result,
  symbols,
  label,
}: {
  result: ResultEnvelope<string, string> | null;
  symbols: string[];
  label: (ticker: string) => string;
}) {
  const t = getMessages().riskChecks;
  const [picked, setPicked] = useState<string | null>(null);
  const ticker = picked && symbols.includes(picked) ? picked : symbols[0];
  const confidence = (result?.meta.parameters as { confidence?: number } | undefined)?.confidence;
  const level = confidence === undefined ? "" : `${+(confidence * 100).toFixed(1)}%`;

  const garch = ticker ? result?.metrics[`${GARCH}:${ticker}`] : undefined;
  const garchSeries = ticker ? result?.series[`${GARCH}:${ticker}`] : undefined;
  const garchRows: [string, string, string][] = [
    ["omega", t.garch.params.omega, show(num(garch, "omega"), (n) => SCIENTIFIC.format(n))],
    ["alpha", t.garch.params.alpha, show(num(garch, "alpha"), (n) => FOUR.format(n))],
    ["beta", t.garch.params.beta, show(num(garch, "beta"), (n) => FOUR.format(n))],
    ["persistence", t.garch.params.persistence, show(num(garch, "persistence"), (n) => FOUR.format(n))],
    [
      "long_run_volatility",
      t.garch.params.longRun,
      show(num(garch, "long_run_volatility"), (n) => formatValue(n, "decimal")),
    ],
    [
      "next_day_volatility",
      t.garch.params.nextDay,
      garch?.status === "ok" && garch.value !== null ? formatValue(garch.value, "decimal") : "–",
    ],
  ];

  return (
    <div data-testid="model-checks" className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-xl">{t.heading}</h2>
        {symbols.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-muted">
            <span>{t.select}</span>
            <select
              value={ticker}
              onChange={(e) => setPicked(e.target.value)}
              className="field w-auto text-ink"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="pb-2 text-left font-medium">
              {t.backtest.caption} {ticker ? `(${ticker})` : ""}
            </caption>
            <thead>
              <tr className="whitespace-nowrap text-left text-muted">
                <th scope="col" className="sticky left-0 bg-paper py-2 pr-3 font-medium">{t.backtest.columns.method}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t.backtest.columns.breaches}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t.backtest.columns.expected}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t.backtest.columns.statistic}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t.backtest.columns.pValue}</th>
                <th scope="col" className="py-2 font-medium">{t.backtest.columns.reading}</th>
              </tr>
            </thead>
            <tbody>
              {BACKTEST_METHODS.map((method) => {
                const r = ticker ? result?.metrics[`${method}:${ticker}`] : undefined;
                const id = `${method}:${ticker ?? "pending"}`;
                return (
                  <tr
                    key={method}
                    data-backtest={id}
                    data-status={r?.status ?? "pending"}
                    className="border-t border-rule"
                  >
                    <th scope="row" className="sticky left-0 bg-paper py-2 pr-3 text-left font-normal">{t.backtest.methods[method]}</th>
                    {r?.status === "ok" && r.value !== null ? (
                      <>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.value}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {show(num(r, "expected_breaches"), (n) => ONE.format(n))}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {show(num(r, "kupiec_statistic"), (n) => TWO.format(n))}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {show(num(r, "p_value"), pValue)}
                        </td>
                        <td
                          data-testid="reading"
                          className={r.details.result === "reject" ? "whitespace-nowrap py-2 text-red-700" : "whitespace-nowrap py-2"}
                        >
                          {r.details.result === "reject" ? t.backtest.reject : t.backtest.accept} {t.backtest.at}{" "}
                          {level}
                        </td>
                      </>
                    ) : (
                      <td colSpan={5} className="py-2 text-muted">
                        {r ? r.reason : getMessages().common.status.pending}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <MetricExplainer explainer={t.backtest.explainer} />
      </div>

      <div className="border-t border-rule pt-6">
        <h3 className="font-body text-sm font-medium tracking-normal">
          {t.garch.heading} {ticker ? `(${ticker})` : ""}
        </h3>
        {garch && garch.status !== "ok" ? (
          <p data-testid="garch-missing" className="mt-2 text-sm text-muted">
            <span className="font-medium">{getMessages().common.status[garch.status]}: </span>
            {garch.reason}
          </p>
        ) : (
          <>
            <div className="mt-2">
              {result && ticker && (
                <LineChart
                  label={t.garch.chartLabel}
                  series={[{ id: ticker, label: ticker, points: chartPoints(garchSeries), color: series(0) }]}
                  xLabel={t.garch.x}
                  formatX={formatChartDate}
                  formatY={formatChartPercent}
                />
              )}
            </div>
            <dl data-testid="garch-parameters" className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              {garchRows.map(([key, name, text]) => (
                <div key={key}>
                  <dt className="text-xs text-muted">{name}</dt>
                  <dd data-garch={key} className="tabular-nums">
                    {text}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        )}
        <MetricExplainer explainer={t.garch.explainer} />
      </div>
    </div>
  );
}
