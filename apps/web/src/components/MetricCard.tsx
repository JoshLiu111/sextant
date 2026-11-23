import { getMessages } from "@/i18n";
import type { MetricResult } from "@/lib/envelope";
import { formatValue } from "@/lib/format";
import { MetricExplainer, type Explainer } from "./MetricExplainer";

export type MetricCardValue = {
  /** Envelope metric id, rendered as `data-metric-value`. */
  id: string;
  /** Optional sub-label when a card shows several values (e.g. "Call" / "Put"). */
  label?: string;
  result: MetricResult | undefined;
  /** Optional line under an ok value, e.g. "Your override". */
  note?: string;
};

type Format = (value: number, unit: MetricResult["unit"]) => string;

/**
 * One metric (or a small group sharing an explainer, like call/put delta) with
 * its explainer. Non-ok values show their status reason instead of a number, so
 * one failed metric never blanks the page.
 */
export function MetricCard({
  id,
  explainer,
  values,
  format = formatValue,
}: {
  /** Card id, rendered as `data-metric`. */
  id: string;
  explainer: Explainer;
  values: MetricCardValue[];
  /** Number formatting by unit; defaults to `formatValue`. */
  format?: Format;
}) {
  return (
    <div data-metric={id} className="rounded-lg border border-black/10 p-4 dark:border-white/15">
      <h3 className="text-sm font-medium text-black/70 dark:text-white/70">{explainer.name}</h3>
      <div className={`mt-1 grid gap-x-4 gap-y-2 ${values.length > 1 ? "grid-cols-2" : ""}`}>
        {values.map((v) => (
          <MetricValue key={v.id} value={v} format={format} />
        ))}
      </div>
      <MetricExplainer explainer={explainer} />
    </div>
  );
}

function MetricValue({ value, format }: { value: MetricCardValue; format: Format }) {
  const t = getMessages().common;
  const r = value.result;
  return (
    <div data-metric-value={value.id} data-status={r?.status ?? "pending"} className="min-w-0">
      {value.label && <div className="text-xs text-black/60 dark:text-white/60">{value.label}</div>}
      {!r ? (
        <div className="text-lg text-black/40 dark:text-white/40">{t.status.pending}</div>
      ) : r.status === "ok" && r.value !== null ? (
        <>
          <div className="font-mono text-xl tabular-nums">{format(r.value, r.unit)}</div>
          {r.unit && t.units[r.unit] && (
            <div className="text-xs text-black/50 dark:text-white/50">{t.units[r.unit]}</div>
          )}
          {value.note && <div className="text-xs text-black/50 dark:text-white/50">{value.note}</div>}
        </>
      ) : r.status === "ok" && r.details.bound === "unlimited" ? (
        <>
          <div className="font-mono text-xl">{t.unlimited}</div>
          {typeof r.details.why === "string" && (
            <div className="text-xs text-black/50 dark:text-white/50">{r.details.why}</div>
          )}
        </>
      ) : (
        <p className={`text-sm ${r.status === "error" ? "text-red-700 dark:text-red-400" : "text-black/60 dark:text-white/60"}`}>
          <span className="font-medium">{t.status[r.status === "ok" ? "error" : r.status]}: </span>
          {r.reason}
        </p>
      )}
    </div>
  );
}
