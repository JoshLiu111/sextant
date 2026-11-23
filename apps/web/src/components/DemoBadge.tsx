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
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
    >
      <span className="rounded bg-amber-400 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-amber-950">
        {t.badge}
      </span>
      <span>{t.body}</span>
    </div>
  );
}
