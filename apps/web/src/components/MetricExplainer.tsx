import { getMessages } from "@/i18n";

/** Copy for one metric's explainer. Keep it in src/i18n, keyed by metric id. */
export type Explainer = { name: string; what: string; how: string; read: string };

/** Collapsible "what it is / how it's computed / how to read it" beside a metric. */
export function MetricExplainer({ explainer }: { explainer: Explainer }) {
  const t = getMessages().common.explainer;
  return (
    <details data-testid="explainer" className="group mt-2 text-sm">
      <summary className="cursor-pointer list-none text-xs text-muted underline decoration-rule decoration-dotted underline-offset-2 hover:text-ink hover:decoration-accent">
        {t.about} {explainer.name}
      </summary>
      <dl className="mt-2 space-y-2 text-ink-2">
        <div>
          <dt className="font-medium">{t.what}</dt>
          <dd>{explainer.what}</dd>
        </div>
        <div>
          <dt className="font-medium">{t.how}</dt>
          <dd className="break-words">{explainer.how}</dd>
        </div>
        <div>
          <dt className="font-medium">{t.read}</dt>
          <dd>{explainer.read}</dd>
        </div>
      </dl>
    </details>
  );
}
