// Browser client for saved valuation assumptions (`/api/compute/valuation/assumptions`).
// The session cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/valuation/saved.py.

import { sendSignedIn, type SignedInOutcome } from "./computeClient";

/** `ValuationAssumptions`: rates as decimals, null = derive (or no price). */
export type ValuationAssumptions = {
  forecast_years: number;
  growth_rate: number;
  terminal_growth: number;
  discount_rate: number | null;
  risk_free_rate: number;
  beta: number;
  equity_risk_premium: number;
  cost_of_equity: number | null;
  cost_of_debt: number | null;
  tax_rate: number | null;
  debt_weight: number | null;
  share_price: number | null;
};

export type AssumptionSet = {
  id: string;
  ticker: string;
  name: string;
  assumptions: ValuationAssumptions;
  created_at: string;
  updated_at: string;
};

/** Numbers are null when the input is empty or not a number, so the API reports the field. */
export type AssumptionSetBody = {
  ticker: string;
  name: string;
  assumptions: Record<keyof ValuationAssumptions, number | null>;
};

export type AssumptionsOutcome<T> = SignedInOutcome<T>;

function send<T>(method: string, suffix: string, body?: unknown): Promise<AssumptionsOutcome<T>> {
  return sendSignedIn<T>(method, `/valuation/assumptions${suffix}`, body);
}

export const valuationAssumptionsApi = {
  list: (ticker: string) =>
    send<AssumptionSet[]>("GET", `?ticker=${encodeURIComponent(ticker)}`),
  save: (body: AssumptionSetBody) => send<AssumptionSet>("POST", "", body),
  remove: (id: string) => send<void>("DELETE", `/${id}`),
};
