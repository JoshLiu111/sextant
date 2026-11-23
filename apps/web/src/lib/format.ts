import type { Unit } from "./envelope";

const fixed = (digits: number) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const FOUR = fixed(4);
const TWO = fixed(2);
const PERCENT = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a metric value by its envelope unit. `decimal` values render as percentages. */
export function formatValue(value: number, unit: Unit | null): string {
  if (unit === "decimal") return PERCENT.format(value);
  return FOUR.format(value);
}

const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/**
 * Financial-statement cell: `currency` and `shares` in millions (no decimals),
 * `per_share` with two decimals. Units are stated once in the table caption.
 */
export function formatStatementValue(value: number, unit: Unit | null): string {
  if (unit === "per_share") return TWO.format(value);
  if (unit === "currency" || unit === "shares") return WHOLE.format(value / 1e6);
  return formatValue(value, unit);
}

const CHART_PERCENT = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Decimal as a one-decimal percentage for chart axes and tooltips (0.123 -> "12.3%"). */
export function formatChartPercent(value: number): string {
  return CHART_PERCENT.format(value);
}

/** Epoch milliseconds (UTC midnight, from an envelope "YYYY-MM-DD" x) back to "YYYY-MM-DD". */
export function formatChartDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Compact two-decimal formatting for chart axes and tooltips. */
export function formatChartNumber(value: number): string {
  return TWO.format(value);
}
