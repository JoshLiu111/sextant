import { getMessages } from "@/i18n";
import type { DataSource } from "@/lib/envelope";

/**
 * Prominent "Demo data" flag. Render it with the result's `source`; it shows only
 * when `source.is_demo`, so a page can never forget to flag synthetic data.
 */
export function DemoBadge({ source }: { source: DataSource | undefined }) {
  if (!source?.is_demo) return null;
  const t = getMessages().common.demo;
  return (
    <div
      role="note"
      data-testid="demo-badge"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-card border border-l-2 border-rule border-l-accent bg-paper-2 px-3 py-2 text-sm text-ink-2"
    >
      <span className="font-medium text-ink">
        {t.badge}
      </span>
      <span>{t.body}</span>
    </div>
  );
}
