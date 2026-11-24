// Shared layout classes for tool pages (issue #70). Structure only: no colour or type.

/**
 * A tool's two columns: the input form on the left, the results on the right
 * (stacked on small screens). Pass the form column's width, e.g. `20rem`:
 *
 *   <div className={toolColumns("20rem")}>
 *     <form className={`${STICKY_INPUTS} space-y-4`}>…</form>
 *     <section data-testid="results" className="min-w-0 space-y-6">…</section>
 *   </div>
 *
 * Widths are listed literally so Tailwind sees each class; add one here if needed.
 */
const COLUMNS = {
  "20rem": "lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]",
  "22rem": "lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]",
} as const;

export function toolColumns(formWidth: keyof typeof COLUMNS): string {
  return `mt-6 grid gap-8 ${COLUMNS[formWidth]}`;
}

/**
 * The input column stays in view while the results scroll, on desktop only
 * (`lg` and up). A form taller than the window scrolls on its own.
 */
export const STICKY_INPUTS =
  "min-w-0 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto";
