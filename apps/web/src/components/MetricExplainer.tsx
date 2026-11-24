"use client";

import { useId, type CSSProperties } from "react";
import { getMessages } from "@/i18n";
import { Formula } from "./Formula";

/** Copy for one metric's explainer. Keep it in src/i18n, keyed by metric id. */
export type Explainer = {
  name: string;
  what: string;
  /** Notes on the computation; with a `formula`, only what the formula doesn't say. */
  how: string;
  read: string;
  /** The computation as LaTeX, rendered as a display formula above `how`. */
  formula?: string;
};

/** A popover id and the CSS anchor name that pins its sheet to the trigger's box. */
export function useExplainerAnchor() {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const popoverId = `explainer-${id}`;
  return {
    popoverId,
    anchorStyle: { "--explainer-anchor": `--${popoverId}` } as CSSProperties,
  };
}

/** The sheet itself: what it is, how it's computed, how to read it. */
export function ExplainerSheet({ id, explainer }: { id: string; explainer: Explainer }) {
  const t = getMessages().common.explainer;
  return (
    <div id={id} popover="auto" className="explainer-pop">
      <p className="mb-3 font-medium text-ink">{explainer.name}</p>
      <dl className="space-y-2 text-ink-2">
        <div>
          <dt className="text-xs text-muted">{t.what}</dt>
          <dd>{explainer.what}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t.how}</dt>
          <dd className="break-words">
            {explainer.formula && <Formula tex={explainer.formula} className="my-1.5" />}
            {explainer.how}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t.read}</dt>
          <dd>{explainer.read}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * "What it is / how it's computed / how to read it" for a metric, in a popover
 * anchored to its trigger, so opening it never reflows the table or card around it.
 * Native `popover`: light dismiss, Escape and focus return come from the browser,
 * and it opens with scripting off. Metric cards use the whole card as the trigger
 * instead (see MetricCard).
 */
export function MetricExplainer({ explainer }: { explainer: Explainer }) {
  const t = getMessages().common.explainer;
  const { popoverId, anchorStyle } = useExplainerAnchor();
  return (
    <div data-testid="explainer" className="explainer mt-2 text-sm" style={anchorStyle}>
      <button type="button" popoverTarget={popoverId} className="explainer-trigger max-w-full truncate">
        {t.about} {explainer.name}
      </button>
      <ExplainerSheet id={popoverId} explainer={explainer} />
    </div>
  );
}
