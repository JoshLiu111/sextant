import { getMessages } from "@/i18n";
import type { MetricResult } from "@/lib/envelope";
import { formatValue } from "@/lib/format";

export type KeyFigure = {
  /** Usually the envelope metric id; rendered as `data-key-figure`. */
  id: string;
  label: string;
  /** Optional line under the label, e.g. the ticker the figure is for. */
  sublabel?: string;
  result: MetricResult | undefined;
};

type Format = (value: number, unit: MetricResult["unit"]) => string;

/**
 * The headline return and risk figures shared by Risk & Performance and the
 * portfolio results (metric ids, without the `:<who>` suffix).
 */
export const RETURN_RISK_FIGURES = ["annualized_return", "annualized_volatility", "max_drawdown", "sharpe"] as const;

/**
 * A row of 3–4 headline figures at the top of a tool's results, picked from
 * metrics the result already has (nothing new is computed). The full metric
 * cards with their explainers still follow further down.
 *
 * Figures carry `data-key-figure` (not `data-metric-value`), so the metric
 * cards stay the only `data-metric-value` elements and existing locators stay
 * unique. A figure that is not ok shows its status, with the reason as a tooltip.
 */
export function KeyFiguresStrip({
  figures,
  format = formatValue,
  label,
}: {
  figures: readonly KeyFigure[];
  /** Number formatting by unit; defaults to `formatValue`. */
  format?: Format;
  /** Accessible name; defaults to "Key figures". */
  label?: string;
}) {
  const t = getMessages().common;
  return (
    <dl
      data-testid="key-figures"
      aria-label={label ?? t.keyFigures}
      className="grid grid-cols-2 gap-4 rounded-lg border border-black/10 p-4 sm:grid-cols-4 dark:border-white/15"
    >
      {figures.map((figure) => (
        <div
          key={figure.id}
          data-key-figure={figure.id}
          data-status={figure.result?.status ?? "pending"}
          className="min-w-0"
        >
          <dt className="text-sm text-black/70 dark:text-white/70">
            {figure.label}
            {figure.sublabel && <span className="block text-xs text-black/50 dark:text-white/50">{figure.sublabel}</span>}
          </dt>
          <dd className="mt-1">
            <FigureValue result={figure.result} format={format} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** One figure's value: the number, "unlimited", or its status when there is no number. */
function FigureValue({ result, format }: { result: MetricResult | undefined; format: Format }) {
  const t = getMessages().common;
  if (!result) return <span className="text-lg text-black/40 dark:text-white/40">{t.status.pending}</span>;
  if (result.status !== "ok") return <FigureStatus result={result} status={t.status[result.status]} />;
  if (result.value !== null) {
    return <span className="font-mono text-xl tabular-nums">{format(result.value, result.unit)}</span>;
  }
  if (result.details.bound === "unlimited") return <span className="font-mono text-xl">{t.unlimited}</span>;
  // "ok" without a number or a bound: shown as an error.
  return <FigureStatus result={result} status={t.status.error} />;
}

function FigureStatus({ result, status }: { result: MetricResult; status: string }) {
  return (
    <span title={result.reason ?? undefined} className="text-sm text-black/60 dark:text-white/60">
      {status}
    </span>
  );
}
