// Chart colours as CSS variables (src/app/tokens.css and globals.css), so a series
// follows the theme in light and dark mode. `SERIES[0]` is the tool's own colour
// (set by `data-tool` on the page's <main>); the rest follow in a fixed order.

export const SERIES = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `var(--color-series-${n})`);

/** The n-th series colour (0-based), cycling past eight. */
export const series = (n: number): string => SERIES[n % SERIES.length];

/** A benchmark or reference series, quieter than the data. */
export const REFERENCE = "var(--color-muted)";

/** A series drawn in ink, e.g. the price under its indicators. */
export const INK = "var(--color-ink)";
