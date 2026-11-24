"use client";

import { useState } from "react";
import { DemoBadge } from "@/components/DemoBadge";
import { ErrorNotice, FieldError, fieldErrorId } from "@/components/ErrorNotice";
import { LineChart, type ChartSeries } from "@/components/LineChart";
import { MetricCard } from "@/components/MetricCard";
import { NumberField } from "@/components/NumberField";
import { getMessages } from "@/i18n";
import type { SeriesResult } from "@/lib/envelope";
import { formatChartDate, formatChartPercent } from "@/lib/format";
import { useCompute } from "@/lib/useCompute";
import { useUrlInputs, writeUrlInputs, type UrlCodec } from "@/lib/urlInputs";

const RULES = ["monthly", "quarterly", "yearly", "drift"] as const;
type Rule = (typeof RULES)[number];

type Settings = { rule: Rule; drift_threshold: string };
const DEFAULTS: Settings = { rule: "quarterly", drift_threshold: "5" };

// Shareable links: `/portfolio?...&rule=drift&drift_threshold=10` (threshold in %).
// Written on every change, since the section has no submit button. An unknown
// rule falls back to the default (a select can't show it).
const URL_CODEC: UrlCodec<Settings> = {
  keys: ["rule", "drift_threshold"],
  read(params) {
    const rule = params.get("rule");
    return {
      rule: RULES.includes(rule as Rule) ? (rule as Rule) : DEFAULTS.rule,
      drift_threshold: params.get("drift_threshold") ?? DEFAULTS.drift_threshold,
    };
  },
  write: (settings) => ({ ...settings }),
};

/** Strategies in `POST /portfolio/rebalancing`: metrics `<metric>:<who>`, series `cumulative_return:<who>`. */
const WHO = ["rebalanced", "buy_and_hold"] as const;
type Who = (typeof WHO)[number];

const RISK_METRICS = [
  "annualized_return",
  "annualized_volatility",
  "max_drawdown",
  "var",
  "cvar",
  "sharpe",
  "sortino",
  "beta",
] as const;
const TRADING_METRICS = ["rebalance_count", "turnover"] as const;

type MetricId = `${(typeof RISK_METRICS)[number]}:${Who}` | `${(typeof TRADING_METRICS)[number]}:rebalanced`;
type SeriesId = `cumulative_return:${Who}`;

const COLORS: Record<Who, { color: string; dashed?: boolean }> = {
  rebalanced: { color: "#2563eb" },
  buy_and_hold: { color: "#d97706", dashed: true },
};

function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Date.parse(String(p.x)), y: p.y }));
}

/**
 * Story 55: backtest a rebalancing rule on the demo portfolio's target weights
 * against buy and hold. `portfolio` is the demo portfolio's request body.
 */
export function RebalancingBacktest({ portfolio }: { portfolio: Record<string, unknown> }) {
  const t = getMessages();
  const r = t.portfolioConstruction.rebalancing;
  const { initial } = useUrlInputs(URL_CODEC);
  const [settings, setSettings] = useState<Settings>(initial);
  const { rule, drift_threshold: threshold } = settings;
  const update = (change: Partial<Settings>) => {
    const next = { ...settings, ...change };
    setSettings(next);
    writeUrlInputs(URL_CODEC, next);
  };
  const setRule = (value: Rule) => update({ rule: value });
  const setThreshold = (value: string) => update({ drift_threshold: value });
  const thresholdValue = threshold.trim() === "" || !Number.isFinite(Number(threshold)) ? null : Number(threshold) / 100;
  const { result, fieldErrors, error } = useCompute<MetricId, SeriesId>("/portfolio/rebalancing", {
    ...portfolio,
    rule,
    drift_threshold: rule === "drift" ? thresholdValue : 0.05,
  });
  // Holding and date errors belong to the demo form; only this section's fields show here.
  const ownErrors = fieldErrors.rule || fieldErrors.drift_threshold;
  const otherErrors = Object.keys(fieldErrors).some((k) => k !== "rule" && k !== "drift_threshold");

  const series: ChartSeries[] = result
    ? WHO.map((who) => ({
        id: who,
        label: r.labels[who],
        points: chartPoints(result.series[`cumulative_return:${who}`]),
        ...COLORS[who],
      }))
    : [];

  return (
    <section aria-labelledby="rebalancing-heading" className="min-w-0 space-y-4">
      <h2 id="rebalancing-heading" className="text-xl font-semibold">
        {r.heading}
      </h2>
      <p className="text-sm text-black/70 dark:text-white/70">{r.intro}</p>
      <div className="grid gap-4 sm:grid-cols-2 lg:max-w-xl">
        <div>
          <label htmlFor="input-rule" className="block text-sm font-medium">
            {r.rule.label}
          </label>
          <select
            id="input-rule"
            name="rule"
            value={rule}
            onChange={(e) => setRule(e.target.value as Rule)}
            aria-describedby={fieldErrors.rule ? fieldErrorId("rule") : "input-rule-hint"}
            className="mt-1 w-full rounded-md border border-black/20 px-3 py-2 dark:border-white/20 dark:bg-white/5"
          >
            {RULES.map((id) => (
              <option key={id} value={id}>
                {r.rule.options[id]}
              </option>
            ))}
          </select>
          <p id="input-rule-hint" className="mt-1 text-xs text-black/50 dark:text-white/50">
            {r.rule.hint}
          </p>
          <FieldError name="rule" message={fieldErrors.rule} />
        </div>
        {rule === "drift" && (
          <NumberField
            name="drift_threshold"
            label={r.threshold.label}
            hint={r.threshold.hint}
            value={threshold}
            onChange={setThreshold}
            error={fieldErrors.drift_threshold}
          />
        )}
      </div>

      <div data-testid="rebalancing-results" className="space-y-6">
        <DemoBadge source={result?.source} />
        {error && !ownErrors && (
          <ErrorNotice title={otherErrors ? t.common.errors.invalidHeading : t.common.errors.heading} message={error} />
        )}
        <div>
          <h3 className="text-lg font-semibold">{r.sections.chart}</h3>
          <div className="mt-2">
            {result && (
              <LineChart
                label={r.chart.label}
                series={series}
                xLabel={r.chart.x}
                formatX={formatChartDate}
                formatY={formatChartPercent}
              />
            )}
          </div>
        </div>
        <div>
          <h3 className="text-lg font-semibold">{r.sections.metrics}</h3>
          <div className="mt-2 grid gap-4 xl:grid-cols-3">
            {RISK_METRICS.map((id) => (
              <MetricCard
                key={id}
                id={`rebalancing-${id}`}
                explainer={t.risk.metrics[id]}
                values={WHO.map((who) => ({
                  id: `${id}:${who}`,
                  label: result ? r.labels[who] : undefined,
                  result: result?.metrics[`${id}:${who}`],
                }))}
              />
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-lg font-semibold">{r.sections.trading}</h3>
          <div className="mt-2 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {TRADING_METRICS.map((id) => (
              <MetricCard
                key={id}
                id={id}
                explainer={r.metrics[id]}
                values={[{ id: `${id}:rebalanced`, result: result?.metrics[`${id}:rebalanced`] }]}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
