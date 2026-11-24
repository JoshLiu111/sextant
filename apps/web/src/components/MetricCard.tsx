import type { CSSProperties } from "react";
import { getMessages } from "@/i18n";
import type { MetricResult } from "@/lib/envelope";
import { formatValue } from "@/lib/format";
import { ExplainerSheet, useExplainerAnchor, type Explainer } from "./MetricExplainer";

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
 * One metric (or a small group sharing an explainer, like call/put delta). The
 * whole card is the explainer's trigger: an info button whose hit area stretches
 * over the card opens the sheet, anchored under the card. Non-ok values show their
 * status reason instead of a number, so one failed metric never blanks the page.
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
  const t = getMessages().common.explainer;
  const { popoverId, anchorStyle } = useExplainerAnchor();
  return (
    <div data-metric={id} className="card metric-card explainer p-4" style={anchorStyle}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 font-body text-sm font-medium tracking-normal text-ink-2">{explainer.name}</h3>
        <button
          type="button"
          popoverTarget={popoverId}
          aria-label={`${t.about} ${explainer.name}`}
          className="metric-card-trigger"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
            <circle cx="8" cy="8" r="6.75" fill="none" stroke="currentColor" strokeWidth="1.25" />
            <path d="M8 7.25v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="8" cy="4.9" r="0.9" fill="currentColor" />
          </svg>
        </button>
      </div>
      {/* Three shared rows (sub-label, figure, unit line) so side-by-side values line up. */}
      <div className={`metric-values pt-6 ${values.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
        {values.map((v) => (
          <MetricValue key={v.id} value={v} format={format} />
        ))}
      </div>
      <div data-testid="explainer">
        <ExplainerSheet id={popoverId} explainer={explainer} />
      </div>
    </div>
  );
}

function MetricValue({ value, format }: { value: MetricCardValue; format: Format }) {
  const t = getMessages().common;
  const r = value.result;
  const meta: string[] = [];
  let figure: string | null = null;
  if (r?.status === "ok" && r.value !== null) {
    figure = format(r.value, r.unit);
    if (r.unit && t.units[r.unit]) meta.push(t.units[r.unit]);
    if (value.note) meta.push(value.note);
  } else if (r?.status === "ok" && r.details.bound === "unlimited") {
    figure = t.unlimited;
    if (typeof r.details.why === "string") meta.push(r.details.why);
  }
  return (
    <div data-metric-value={value.id} data-status={r?.status ?? "pending"} className="metric-value">
      <div className="text-xs text-muted">{value.label}</div>
      {!r ? (
        <div className="text-lg text-muted">{t.status.pending}</div>
      ) : figure !== null ? (
        // The figure shrinks to fit its column, by its length, never below body size.
        <div className="metric-figure-box">
          <div
            className="figure-display metric-figure text-ink"
            style={{ "--chars": figure.length } as CSSProperties}
          >
            {figure}
          </div>
        </div>
      ) : (
        <p className={`text-sm ${r.status === "error" ? "text-error" : "text-muted"}`}>
          <span className="font-medium">{t.status[r.status === "ok" ? "error" : r.status]}: </span>
          {r.reason}
        </p>
      )}
      <div className="text-xs text-muted">
        {meta.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
    </div>
  );
}
