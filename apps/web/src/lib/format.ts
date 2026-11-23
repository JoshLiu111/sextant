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

/** Format a metric value by its envelope unit. `decimal` values render as percentages; `money` as an amount with 2 decimals. */
export function formatValue(value: number, unit: Unit | null): string {
  if (unit === "decimal") return PERCENT.format(value);
  if (unit === "percent") return `${TWO.format(value)}%`;
  if (unit === "percentage_points") return `${TWO.format(value)} pp`;
  if (unit === "ratio") return TWO.format(value);
  if (unit === "money") return TWO.format(value);
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

const CHART_ONE = fixed(1);

/** A value already in percent (4.5 means 4.5%) for chart axes and tooltips: "4.5%". */
export function formatChartPercentValue(value: number): string {
  return `${CHART_ONE.format(value)}%`;
}

const USD_COMPACT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });

/**
 * Company-scale amounts: `currency` compact ("$66.99B"), `per_share` in dollars
 * ("$150.58"), `shares` compact ("7.43B"); other units as `formatValue`.
 */
export function formatMoneyValue(value: number, unit: Unit | null): string {
  if (unit === "currency") return USD_COMPACT.format(value);
  if (unit === "per_share") return USD.format(value);
  if (unit === "shares") return COMPACT.format(value);
  return formatValue(value, unit);
}

/** ISO 8601 timestamp with offset to "YYYY-MM-DD HH:MM UTC". */
export function formatTimestampUtc(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** Percentage points (a spread between two percent values) for charts: "-0.25 pp". */
export function formatChartPercentPoints(value: number): string {
  return `${TWO.format(value)} pp`;
}

const MATURITY = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** A maturity in years for charts: under a year in months ("1.5 mo"), else years ("10 yr"). */
export function formatChartMaturity(years: number): string {
  if (years < 1) return `${MATURITY.format(Math.round(years * 12 * 10) / 10)} mo`;
  return `${MATURITY.format(years)} yr`;
}
