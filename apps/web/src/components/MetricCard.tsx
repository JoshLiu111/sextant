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
    <div data-metric={id} className="card p-4">
      <h3 className="font-body text-sm font-medium tracking-normal text-ink-2">{explainer.name}</h3>
      <div className={`mt-2 grid gap-x-4 gap-y-2 ${values.length > 1 ? "grid-cols-2" : ""}`}>
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
      {value.label && <div className="text-xs text-muted">{value.label}</div>}
      {!r ? (
        <div className="text-lg text-muted">{t.status.pending}</div>
      ) : r.status === "ok" && r.value !== null ? (
        <>
          <div className="figure-display text-xl text-ink">{format(r.value, r.unit)}</div>
          {r.unit && t.units[r.unit] && (
            <div className="text-xs text-muted">{t.units[r.unit]}</div>
          )}
          {value.note && <div className="text-xs text-muted">{value.note}</div>}
        </>
      ) : r.status === "ok" && r.details.bound === "unlimited" ? (
        <>
          <div className="figure-display text-xl text-ink">{t.unlimited}</div>
          {typeof r.details.why === "string" && (
            <div className="text-xs text-muted">{r.details.why}</div>
          )}
        </>
      ) : (
        <p className={`text-sm ${r.status === "error" ? "text-error" : "text-muted"}`}>
          <span className="font-medium">{t.status[r.status === "ok" ? "error" : r.status]}: </span>
          {r.reason}
        </p>
      )}
    </div>
  );
}
