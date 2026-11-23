// Form helpers shared by the Options Calculator tabs. Form values are strings in
// display units (percent); request models use decimals.

import type { SeriesResult } from "@/lib/envelope";

/** Market inputs every options endpoint takes (`MarketInputs` in the compute API). */
export type MarketForm = {
  spot: string;
  time_to_expiry: string;
  volatility: string;
  risk_free_rate: string;
  dividend_yield: string;
};
export type MarketField = keyof MarketForm;

export const MARKET_DEFAULTS: MarketForm = {
  spot: "100",
  time_to_expiry: "1",
  volatility: "20",
  risk_free_rate: "5",
  dividend_yield: "0",
};

export const MARKET_FIELDS: MarketField[] = ["spot", "time_to_expiry", "volatility", "risk_free_rate", "dividend_yield"];

const PERCENT_FIELDS = new Set<string>(["volatility", "risk_free_rate", "dividend_yield"]);

/** Empty or non-numeric input goes to the API as null so it reports the field. */
export function toNumber(raw: string, percent = false): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return percent ? n / 100 : n;
}

export function isPercentField(field: string): boolean {
  return PERCENT_FIELDS.has(field);
}

export function marketRequest(form: MarketForm): Record<MarketField, number | null> {
  return Object.fromEntries(MARKET_FIELDS.map((f) => [f, toNumber(form[f], isPercentField(f))])) as Record<
    MarketField,
    number | null
  >;
}

/** Chart points from an envelope series with numeric x; empty unless the series is ok. */
export function chartPoints(series: SeriesResult | undefined) {
  if (!series || series.status !== "ok") return [];
  return series.points.map((p) => ({ x: Number(p.x), y: p.y }));
}
