import type { ReactNode } from "react";

/** A series' source, units, frequency and last update, as a definition list (testid `series-meta`). */
export function MetaList({ rows }: { rows: { label: string; value: ReactNode }[] }) {
  return (
    <dl
      data-testid="series-meta"
      className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm text-black/70 dark:text-white/70"
    >
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="font-medium">{row.label}</dt>
          <dd className="min-w-0 break-words">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
