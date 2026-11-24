"use client";

import { useId, type CSSProperties } from "react";
import { getMessages } from "@/i18n";

/** Copy for one metric's explainer. Keep it in src/i18n, keyed by metric id. */
export type Explainer = { name: string; what: string; how: string; read: string };

/**
 * "What it is / how it's computed / how to read it" for a metric, in a popover
 * anchored to its trigger, so opening it never reflows the table or card around it.
 * Native `popover`: light dismiss, Escape and focus return come from the browser,
 * and it opens with scripting off.
 */
export function MetricExplainer({ explainer }: { explainer: Explainer }) {
  const t = getMessages().common.explainer;
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const popoverId = `explainer-${id}`;
  return (
    <div
      data-testid="explainer"
      className="explainer mt-2 text-sm"
      style={{ "--explainer-anchor": `--${popoverId}` } as CSSProperties}
    >
      <button type="button" popoverTarget={popoverId} className="explainer-trigger">
        {t.about} {explainer.name}
      </button>
      <div id={popoverId} popover="auto" className="explainer-pop">
        <dl className="space-y-2 text-ink-2">
          <div>
            <dt className="text-xs text-muted">{t.what}</dt>
            <dd>{explainer.what}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t.how}</dt>
            <dd className="break-words">{explainer.how}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t.read}</dt>
            <dd>{explainer.read}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
