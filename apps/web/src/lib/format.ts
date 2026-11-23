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

/** Compact two-decimal formatting for chart axes and tooltips. */
export function formatChartNumber(value: number): string {
  return TWO.format(value);
}
